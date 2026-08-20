"""Port of `EpaperReaderController` + `EpaperQuestionApiController` query logic.

Soft-delete note: `EpaperPublication`/`EpaperEdition`/`EpaperEditionPage`/
`EpaperRegion` use Eloquent's `SoftDeletes` (via `SoftDeletesWithDeleter`),
which installs an automatic global scope in Laravel. SQLAlchemy has no such
scope, so EVERY query against these 4 tables below explicitly filters
`deleted_at IS NULL`.

Missing-source-class reconstructions (see porting spec's "unresolved
dependencies" section — these classes do not exist anywhere in the Laravel
repo or its git history):
  - `App\\Support\\QuizParticipantPhone` -> `app/core/phone.py::normalize_phone`
    (used here, not reimplemented in this file).
  - `App\\Support\\EpaperCropDownloadImage` -> reconstructed below with
    Pillow (`_merge_vertical` / `_apply_watermark`), documented at each
    function since the exact original asset/placement is unknown.
  - `App\\Support\\EpaperApiCache` -> intentionally NOT ported. It is pure
    cache-invalidation plumbing for the admin/write side; this pass has no
    caching layer at all (plain DB reads only), so there is nothing to
    invalidate and nothing to port for the read-only routes in scope here.
"""

import asyncio
import re
from datetime import date
from io import BytesIO

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import HTTPException
from fastapi.responses import JSONResponse
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core import portal_time
from app.core.config import settings
from app.core.media import get_media_url
from app.core.phone import normalize_phone
from app.models.epaper import (
    EpaperEdition,
    EpaperEditionPage,
    EpaperPublication,
    EpaperQuestion,
    EpaperQuestionAnswer,
    EpaperQuestionOption,
    EpaperRegion,
)
from app.models.news import News
from app.models.participant import Participant

GRID_PAGES = 16


def _model_not_found(name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{name}].")


def _php_int_cast(value: str) -> int:
    """Mirrors PHP's `(int) $value` cast: parses a leading optional sign +
    digit run and ignores everything else; non-numeric input casts to 0."""
    match = re.match(r"^\s*[-+]?\d+", value)
    return int(match.group()) if match else 0


def _present(value: str | None) -> bool:
    """Mirrors the `$x !== null && $x !== ''` / Laravel `filled()`-style checks
    used for `revision`/`region_id`/`head_region_id`/`tail_region_id` query
    params (as opposed to full PHP truthiness — "0" is a legitimate id and
    must NOT be treated as absent here)."""
    return value is not None and value != ""


def _parse_date_or_404(date_str: str) -> date:
    try:
        return date.fromisoformat(date_str)
    except ValueError as exc:
        # BUG FIX vs source: `Carbon::parse($date)` on a genuinely unparseable
        # date string throws an uncaught exception in the Laravel app (-> 500).
        # We treat it as "no such edition" (404) instead — the same externally
        # observable "not found" outcome, without the raw 500.
        raise _model_not_found("EpaperEdition") from exc


# ---------------------------------------------------------------------------
# Publications list
# ---------------------------------------------------------------------------


async def get_publications(db: AsyncSession) -> list[dict]:
    has_published_edition = (
        select(EpaperEdition.id)
        .where(
            EpaperEdition.epaper_publication_id == EpaperPublication.id,
            EpaperEdition.status == "published",
            EpaperEdition.deleted_at.is_(None),
        )
        .correlate(EpaperPublication)
        .exists()
    )
    stmt = (
        select(EpaperPublication.id, EpaperPublication.name, EpaperPublication.slug)
        .where(EpaperPublication.deleted_at.is_(None), has_published_edition)
        .order_by(EpaperPublication.created_at)
    )
    rows = (await db.execute(stmt)).all()
    return [{"id": r.id, "name": r.name, "slug": r.slug} for r in rows]


# ---------------------------------------------------------------------------
# Reader edition resolution (shared by show / download-crops / download-page)
# ---------------------------------------------------------------------------


async def _get_publication_or_404(db: AsyncSession, slug: str) -> EpaperPublication:
    # `epaper_publications.slug` has NO DB-level uniqueness at all post-migration
    # (confirmed in the porting spec) — `.limit(1)`/first-match-wins is correct
    # parity with Laravel's `firstOrFail()`, not a bug to fix.
    stmt = (
        select(EpaperPublication)
        .where(EpaperPublication.slug == slug, EpaperPublication.deleted_at.is_(None))
        .limit(1)
    )
    publication = (await db.execute(stmt)).scalars().first()
    if publication is None:
        raise _model_not_found("EpaperPublication")
    return publication


async def _find_reader_edition_on_date(
    db: AsyncSession, publication_id: int, day: date, revision_input: str | None
) -> EpaperEdition | None:
    stmt = select(EpaperEdition).where(
        EpaperEdition.epaper_publication_id == publication_id,
        EpaperEdition.status == "published",
        EpaperEdition.deleted_at.is_(None),
        EpaperEdition.publication_date == day,
    )
    if _present(revision_input):
        stmt = stmt.where(EpaperEdition.revision == _php_int_cast(revision_input))
    else:
        stmt = stmt.order_by(EpaperEdition.revision.desc())
    stmt = stmt.limit(1)
    return (await db.execute(stmt)).scalars().first()


async def resolve_reader_edition(
    db: AsyncSession, slug: str, date_str: str, revision_input: str | None
) -> tuple[EpaperPublication, EpaperEdition]:
    publication = await _get_publication_or_404(db, slug)
    day = _parse_date_or_404(date_str)

    edition = await _find_reader_edition_on_date(db, publication.id, day, revision_input)
    if edition is not None:
        return publication, edition

    fallback_stmt = (
        select(EpaperEdition.publication_date)
        .where(
            EpaperEdition.epaper_publication_id == publication.id,
            EpaperEdition.status == "published",
            EpaperEdition.deleted_at.is_(None),
            EpaperEdition.publication_date <= day,
        )
        .order_by(EpaperEdition.publication_date.desc())
        .limit(1)
    )
    fallback_date = (await db.execute(fallback_stmt)).scalars().first()
    if fallback_date is None:
        raise _model_not_found("EpaperEdition")

    edition = await _find_reader_edition_on_date(db, publication.id, fallback_date, revision_input)
    if edition is None:
        raise _model_not_found("EpaperEdition")
    return publication, edition


async def _region_on_edition_or_404(db: AsyncSession, region_id: int, edition_id: int) -> EpaperRegion:
    stmt = (
        select(EpaperRegion)
        .join(EpaperEditionPage, EpaperRegion.epaper_edition_page_id == EpaperEditionPage.id)
        .where(
            EpaperRegion.id == region_id,
            EpaperRegion.deleted_at.is_(None),
            EpaperEditionPage.epaper_edition_id == edition_id,
            EpaperEditionPage.deleted_at.is_(None),
        )
    )
    region = (await db.execute(stmt)).scalars().first()
    if region is None:
        raise _model_not_found("EpaperRegion")
    return region


# ---------------------------------------------------------------------------
# Reader `show` payload
# ---------------------------------------------------------------------------


async def _load_pages_with_regions(
    db: AsyncSession, edition_id: int
) -> list[tuple[EpaperEditionPage, list[EpaperRegion]]]:
    pages_stmt = (
        select(EpaperEditionPage)
        .where(EpaperEditionPage.epaper_edition_id == edition_id, EpaperEditionPage.deleted_at.is_(None))
        .order_by(EpaperEditionPage.page_number)
    )
    pages = (await db.execute(pages_stmt)).scalars().all()
    if not pages:
        return []

    page_ids = [p.id for p in pages]
    regions_stmt = (
        select(EpaperRegion)
        .where(EpaperRegion.epaper_edition_page_id.in_(page_ids), EpaperRegion.deleted_at.is_(None))
        .options(selectinload(EpaperRegion.news).selectinload(News.details))
        .order_by(EpaperRegion.id)
    )
    regions = (await db.execute(regions_stmt)).scalars().all()

    grouped: dict[int, list[EpaperRegion]] = {}
    for r in regions:
        grouped.setdefault(r.epaper_edition_page_id, []).append(r)

    return [(p, grouped.get(p.id, [])) for p in pages]


def _serialize_region(region: EpaperRegion) -> dict:
    news = region.news
    # Linked news is included when present regardless of `News.published` —
    # epaper regions are curated by editors (per the source resource's own
    # docblock). We DO still gate on the linked news row not being
    # soft-deleted (`deleted_at IS NULL`), matching every other public-facing
    # News query in this codebase (see app/routers/news.py), even though the
    # source spec text only calls out the `published` non-gate explicitly.
    news_visible = news is not None and news.deleted_at is None
    news_payload = None
    if news_visible:
        news_payload = {
            "id": news.id,
            "image_url": get_media_url(news.image),
            "details_html": news.details.details if news.details is not None else None,
        }
    linked_id_str = str(region.linked_region_id) if region.linked_region_id is not None else None
    return {
        "id": region.id,
        "epaper_edition_page_id": region.epaper_edition_page_id,
        "role": region.role,
        "title": region.title,
        "url": region.external_url or "",
        "x": float(region.x_pct),
        "y": float(region.y_pct),
        "width": float(region.width_pct),
        "height": float(region.height_pct),
        "crop_image_url": get_media_url(region.crop_image_path),
        "linkedAnnotationId": linked_id_str,
        "linked_annotation_id": linked_id_str,
        "news_id": region.news_id,
        "news_title": news.title if news_visible else "",
        "news": news_payload,
    }


def _serialize_page(page: EpaperEditionPage, regions: list[EpaperRegion]) -> dict:
    return {
        "id": str(page.id),
        "page_number": page.page_number,
        "image": get_media_url(page.image_path),
        "annotations": [_serialize_region(r) for r in regions],
    }


async def get_reader_show(db: AsyncSession, slug: str, date_str: str, revision_input: str | None) -> dict:
    publication, edition = await resolve_reader_edition(db, slug, date_str, revision_input)
    pages_with_regions = await _load_pages_with_regions(db, edition.id)

    avail_stmt = (
        select(EpaperEdition.id, EpaperEdition.revision)
        .where(
            EpaperEdition.epaper_publication_id == publication.id,
            EpaperEdition.status == "published",
            EpaperEdition.deleted_at.is_(None),
            EpaperEdition.publication_date == edition.publication_date,
        )
        .order_by(EpaperEdition.revision)
    )
    rows = (await db.execute(avail_stmt)).all()
    available_revisions = [{"edition_id": r.id, "revision": r.revision} for r in rows]

    return {
        "publication": {"slug": publication.slug, "name": publication.name},
        "edition": {
            "id": edition.id,
            "publication_date": edition.publication_date.isoformat() if edition.publication_date else None,
            "title": edition.title,
            "revision": edition.revision,
        },
        "pages": [_serialize_page(p, regions) for p, regions in pages_with_regions],
        "available_revisions": available_revisions,
    }


# ---------------------------------------------------------------------------
# Image fetch/processing (reconstruction of the missing
# `App\Support\EpaperCropDownloadImage`; see module docstring)
# ---------------------------------------------------------------------------


def _s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="auto",
    )


def _fetch_object_bytes_sync(path: str) -> bytes:
    client = _s3_client()
    try:
        obj = client.get_object(Bucket=settings.r2_bucket, Key=path.lstrip("/"))
        return obj["Body"].read()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("NoSuchKey", "404"):
            raise _model_not_found("EpaperImage") from exc
        raise


async def _fetch_object_bytes(path: str) -> bytes:
    # boto3 is a blocking/synchronous client; run it off the event loop.
    return await asyncio.to_thread(_fetch_object_bytes_sync, path)


def _watermark_text_layer(size: tuple[int, int], tiled: bool) -> Image.Image:
    """Best-effort reconstruction of the missing `EpaperCropDownloadImage`
    watermarking behavior (not present anywhere in the source repo/git
    history — see module docstring). The exact original watermark
    asset/placement/JPEG quality are unknown; this is a real, working
    replacement chosen to be reasonable, not a byte-for-byte port:
      - tiled=True (single crop downloads, matching the source call site
        which omits the 3rd `EpaperCropDownloadImage::fromStoragePath()` arg
        and so gets its default): a diagonal repeating watermark, since small
        crops are easy to re-crop around a single fixed mark.
      - tiled=False (full edition page scan downloads, matching the source's
        explicit `false` 3rd argument): a single semi-transparent centered
        watermark — this lines up with the `downloadPage()` docblock, which
        literally says "JPEG with center watermark only".
    """
    overlay = Image.new("RGBA", size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    text = "AGAMIRSOMOY.COM"
    font_size = max(16, min(size) // 12)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]

    if tiled:
        step_x, step_y = text_w + 60, text_h + 60
        row = 0
        y = -step_y
        while y < size[1] + step_y:
            x_offset = (step_x // 2) if row % 2 else 0
            x = -step_x + x_offset
            while x < size[0] + step_x:
                draw.text((x, y), text, font=font, fill=(255, 255, 255, 90))
                x += step_x
            y += step_y
            row += 1
    else:
        x = (size[0] - text_w) / 2
        y = (size[1] - text_h) / 2
        draw.text((x, y), text, font=font, fill=(255, 255, 255, 130))

    return overlay


def _apply_watermark_sync(image_bytes: bytes, tiled: bool) -> bytes:
    base = Image.open(BytesIO(image_bytes)).convert("RGBA")
    overlay = _watermark_text_layer(base.size, tiled)
    watermarked = Image.alpha_composite(base, overlay).convert("RGB")
    buf = BytesIO()
    watermarked.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _merge_vertical_sync(head_bytes: bytes, tail_bytes: bytes) -> bytes:
    """Reconstruction of `EpaperCropDownloadImage::mergeVerticalFromStorage()`:
    stacks the head image above the tail image (same width), no watermark
    applied (the source call site never passes a watermark flag to the merge
    method — only the single-crop/full-page paths do)."""
    head = Image.open(BytesIO(head_bytes)).convert("RGB")
    tail = Image.open(BytesIO(tail_bytes)).convert("RGB")
    width = max(head.width, tail.width)
    if head.width != width:
        head = head.resize((width, round(head.height * width / head.width)))
    if tail.width != width:
        tail = tail.resize((width, round(tail.height * width / tail.width)))
    merged = Image.new("RGB", (width, head.height + tail.height), (255, 255, 255))
    merged.paste(head, (0, 0))
    merged.paste(tail, (0, head.height))
    buf = BytesIO()
    merged.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


async def image_from_storage(path: str, *, tiled: bool) -> bytes:
    raw = await _fetch_object_bytes(path)
    return await asyncio.to_thread(_apply_watermark_sync, raw, tiled)


async def merge_vertical_from_storage(head_path: str, tail_path: str) -> bytes:
    head_raw = await _fetch_object_bytes(head_path)
    tail_raw = await _fetch_object_bytes(tail_path)
    return await asyncio.to_thread(_merge_vertical_sync, head_raw, tail_raw)


# ---------------------------------------------------------------------------
# download-crops / download-page
# ---------------------------------------------------------------------------


def _regions_are_linked_pair(a: EpaperRegion, b: EpaperRegion) -> bool:
    a_linked = a.linked_region_id or 0
    b_linked = b.linked_region_id or 0
    return a_linked == b.id or b_linked == a.id


def _order_head_tail(a: EpaperRegion, b: EpaperRegion) -> tuple[EpaperRegion, EpaperRegion] | None:
    ordered = sorted([a, b], key=lambda r: 0 if r.role == EpaperRegion.ROLE_HEAD else 1)
    if ordered[0].role != EpaperRegion.ROLE_HEAD or ordered[1].role != EpaperRegion.ROLE_TAIL:
        return None
    return ordered[0], ordered[1]


async def get_crop_download(
    db: AsyncSession,
    *,
    edition_id: int,
    head_region_id: str | None,
    tail_region_id: str | None,
    region_id: str | None,
) -> tuple[bytes, str]:
    """Returns (jpeg_bytes, filename_suffix)."""
    if _present(head_region_id) and _present(tail_region_id):
        head = await _region_on_edition_or_404(db, _php_int_cast(head_region_id), edition_id)
        tail = await _region_on_edition_or_404(db, _php_int_cast(tail_region_id), edition_id)
        if not head.crop_image_path or not tail.crop_image_path:
            raise HTTPException(status_code=404)
        if not _regions_are_linked_pair(head, tail):
            raise HTTPException(status_code=404)
        ordered = _order_head_tail(head, tail)
        if ordered is None:
            raise HTTPException(status_code=404)
        head_ordered, tail_ordered = ordered
        binary = await merge_vertical_from_storage(head_ordered.crop_image_path, tail_ordered.crop_image_path)
        return binary, "head-tail"

    if _present(region_id):
        region = await _region_on_edition_or_404(db, _php_int_cast(region_id), edition_id)
        if not region.crop_image_path:
            raise HTTPException(status_code=404)
        binary = await image_from_storage(region.crop_image_path, tiled=True)
        return binary, f"clip-{region.id}"

    raise HTTPException(status_code=404)


async def get_page_download(
    db: AsyncSession, *, edition_id: int, page_number_raw: str | None
) -> tuple[bytes, int]:
    page_number: int | None = None
    if _present(page_number_raw):
        try:
            page_number = int(page_number_raw)
        except ValueError:
            page_number = None
    if page_number is None or page_number < 1:
        raise HTTPException(status_code=404)

    stmt = select(EpaperEditionPage).where(
        EpaperEditionPage.epaper_edition_id == edition_id,
        EpaperEditionPage.page_number == page_number,
        EpaperEditionPage.deleted_at.is_(None),
    )
    page = (await db.execute(stmt)).scalars().first()
    if page is None:
        raise _model_not_found("EpaperEditionPage")
    if not page.image_path:
        raise HTTPException(status_code=404)

    binary = await image_from_storage(page.image_path, tiled=False)
    return binary, page_number


# ---------------------------------------------------------------------------
# Epaper questions: grid / page / detail
# ---------------------------------------------------------------------------


def parse_publish_day(raw: str | None) -> date:
    if raw is None or raw.strip() == "":
        return portal_time.now().date()
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid publish_date") from exc


async def get_grid(db: AsyncSession, publish_date_raw: str | None) -> dict:
    publish_day = parse_publish_day(publish_date_raw)
    slots = []
    for page_number in range(1, GRID_PAGES + 1):
        stmt = (
            select(EpaperQuestion)
            .where(
                EpaperQuestion.is_active.is_(True),
                func.trim(EpaperQuestion.page_number) == str(page_number),
                EpaperQuestion.publish_date == publish_day,
            )
            .order_by(EpaperQuestion.id.desc())
            .limit(1)
        )
        latest = (await db.execute(stmt)).scalars().first()
        slots.append(
            {
                "page_number": page_number,
                "question": (
                    {
                        "id": latest.id,
                        "title": latest.title,
                        "publish_date": latest.publish_date.isoformat() if latest.publish_date else None,
                    }
                    if latest is not None
                    else None
                ),
            }
        )
    return {"publish_date": publish_day.isoformat(), "slots": slots}


def _serialize_question(question: EpaperQuestion, *, include_options: bool) -> dict:
    payload = {
        "id": question.id,
        "title": question.title,
        "description": None,  # no such DB column; the source resource hardcodes null too
        "page_number": question.page_number,
        "publish_date": question.publish_date.isoformat() if question.publish_date else None,
    }
    if include_options:
        payload["options"] = [
            {"id": o.id, "question_id": o.epaper_question_id, "option_text": o.option_text}
            for o in question.options
        ]
    return payload


async def get_page_questions(db: AsyncSession, page_number: int, publish_date_raw: str | None) -> dict:
    if page_number < 1 or page_number > GRID_PAGES:
        raise HTTPException(status_code=404)

    publish_day = parse_publish_day(publish_date_raw)
    stmt = (
        select(EpaperQuestion)
        .where(
            EpaperQuestion.is_active.is_(True),
            func.trim(EpaperQuestion.page_number) == str(page_number),
            EpaperQuestion.publish_date == publish_day,
        )
        .options(selectinload(EpaperQuestion.options))
        .order_by(EpaperQuestion.id.desc())
    )
    questions = (await db.execute(stmt)).scalars().all()
    return {
        "publish_date": publish_day.isoformat(),
        "page_number": page_number,
        "data": [_serialize_question(q, include_options=True) for q in questions],
    }


async def get_question_detail(db: AsyncSession, question_id: int) -> dict:
    stmt = (
        select(EpaperQuestion)
        .where(EpaperQuestion.id == question_id, EpaperQuestion.is_active.is_(True))
        .options(selectinload(EpaperQuestion.options))
    )
    question = (await db.execute(stmt)).scalars().first()
    if question is None:
        raise _model_not_found("EpaperQuestion")
    return _serialize_question(question, include_options=True)


# ---------------------------------------------------------------------------
# Participation / answer submission
# ---------------------------------------------------------------------------


def _validation_error(errors: dict[str, list[str]]) -> JSONResponse:
    """Mirrors Laravel's standard FormRequest validation-failure JSON shape."""
    return JSONResponse(status_code=422, content={"message": "The given data was invalid.", "errors": errors})


async def _question_exists(db: AsyncSession, question_id: int) -> bool:
    stmt = select(EpaperQuestion.id).where(EpaperQuestion.id == question_id)
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def _option_exists_for_question(db: AsyncSession, option_id: int, question_id: int) -> bool:
    stmt = select(EpaperQuestionOption.id).where(
        EpaperQuestionOption.id == option_id,
        EpaperQuestionOption.epaper_question_id == question_id,
    )
    return (await db.execute(stmt)).scalar_one_or_none() is not None


async def get_participation(db: AsyncSession, question_id: int, phone: str) -> dict | JSONResponse:
    normalized_phone = normalize_phone(phone)
    errors: dict[str, list[str]] = {}
    if not await _question_exists(db, question_id):
        errors["question_id"] = ["The selected question id is invalid."]
    if not normalized_phone:
        errors["phone"] = ["The phone field is required."]
    elif len(normalized_phone) < 10 or len(normalized_phone) > 20:
        errors["phone"] = ["The phone field must be between 10 and 20 characters."]
    if errors:
        return _validation_error(errors)

    question = (
        await db.execute(
            select(EpaperQuestion).where(EpaperQuestion.id == question_id, EpaperQuestion.is_active.is_(True))
        )
    ).scalars().first()
    if question is None:
        # NOT an HTTPException: the spec requires this exact flat body
        # (`{"already_answered": false}`) with no `detail`/`message` wrapper.
        return JSONResponse(status_code=404, content={"already_answered": False})

    participant = (
        await db.execute(select(Participant).where(Participant.phone == normalized_phone))
    ).scalars().first()
    if participant is None:
        return {"already_answered": False}

    answered = (
        await db.execute(
            select(EpaperQuestionAnswer.id).where(
                EpaperQuestionAnswer.epaper_question_id == question.id,
                EpaperQuestionAnswer.participant_id == participant.id,
            )
        )
    ).scalar_one_or_none() is not None
    return {"already_answered": answered}


async def submit_answer(
    db: AsyncSession,
    *,
    question_id: int,
    question_option_id: int,
    phone: str,
    name: str | None,
    email: str | None,
) -> JSONResponse:
    normalized_phone = normalize_phone(phone)
    errors: dict[str, list[str]] = {}

    if not await _question_exists(db, question_id):
        errors["question_id"] = ["The selected question id is invalid."]

    option_ok = True
    if not await _option_exists_for_question(db, question_option_id, question_id):
        errors["question_option_id"] = ["The selected question option id is invalid."]
        option_ok = False

    if not normalized_phone:
        errors["phone"] = ["Mobile number is required."]
    elif len(normalized_phone) < 10 or len(normalized_phone) > 20:
        errors["phone"] = ["The phone field must be between 10 and 20 characters."]

    # "known participant" check runs against the (already-normalized) phone,
    # exactly like the source FormRequest's conditional `name` rule.
    known_participant = False
    if normalized_phone:
        known_participant = (
            await db.execute(select(Participant.id).where(Participant.phone == normalized_phone))
        ).scalar_one_or_none() is not None

    name_clean = (name or "").strip()
    if not known_participant and not name_clean:
        errors["name"] = ["Name is required for new participants."]
    elif name_clean and len(name_clean) > 50:
        errors["name"] = ["The name field must not be greater than 50 characters."]

    email_clean = (email or "").strip() or None
    if email_clean and (len(email_clean) > 99 or "@" not in email_clean):
        errors["email"] = ["The email field must be a valid email address."]

    if errors:
        return _validation_error(errors)

    question = (
        await db.execute(
            select(EpaperQuestion).where(EpaperQuestion.id == question_id, EpaperQuestion.is_active.is_(True))
        )
    ).scalars().first()
    if question is None:
        raise _model_not_found("EpaperQuestion")

    option = None
    if option_ok:
        option = (
            await db.execute(
                select(EpaperQuestionOption).where(
                    EpaperQuestionOption.id == question_option_id,
                    EpaperQuestionOption.epaper_question_id == question.id,
                )
            )
        ).scalars().first()
    if option is None:
        raise _model_not_found("EpaperQuestionOption")

    participant = (
        await db.execute(select(Participant).where(Participant.phone == normalized_phone))
    ).scalars().first()
    if participant is None:
        participant = Participant(phone=normalized_phone, name=name_clean, email=email_clean)
        db.add(participant)
        await db.flush()

    already = (
        await db.execute(
            select(EpaperQuestionAnswer.id).where(
                EpaperQuestionAnswer.epaper_question_id == question.id,
                EpaperQuestionAnswer.participant_id == participant.id,
            )
        )
    ).scalar_one_or_none() is not None
    if already:
        await db.rollback()
        return JSONResponse(status_code=422, content={"message": "Already answered.", "already_answered": True})

    answer = EpaperQuestionAnswer(
        epaper_question_id=question.id,
        participant_id=participant.id,
        epaper_question_option_id=option.id,
        is_correct=bool(option.is_correct),
        answered_at=portal_time.now(),
    )
    db.add(answer)
    try:
        await db.commit()
    except IntegrityError:
        # Race: two concurrent submits for the same participant+question both
        # pass the `already` check above, then collide on the DB-level unique
        # constraint `(epaper_question_id, participant_id)`. Translate that
        # into the SAME friendly "Already answered" 422 the app-level check
        # produces, instead of letting a raw 500 surface.
        await db.rollback()
        return JSONResponse(status_code=422, content={"message": "Already answered.", "already_answered": True})

    return JSONResponse(status_code=201, content={"message": "Submitted.", "already_answered": False})
