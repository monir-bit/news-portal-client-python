from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import portal_time
from app.core.database import get_db
from app.core.media import get_media_url
from app.core.pagination import cursor_page_envelope, keyset_paginate
from app.core.rate_limit import SEARCH, limiter
from app.core.seo import make_seo
from app.models.category import Category
from app.models.layout import PageCategoryMap
from app.models.news import Author, News, NewsRead, Tag
from app.queries.applications import (
    latest_news,
    linked_news,
    most_read_news,
    most_read_news_by_category,
    news_timelines,
)
from app.queries.category_news_page_service import (
    apply_date_filter,
    apply_geo_filter,
    base_news_query,
    build_full_listing_payload,
    categories_ordered_for_print_edition,
    category_ids_for_slug,
    paginate_after_leads,
    resolve_visible_category,
)
from app.queries.news_category_home import (
    news_by_category_home,
    news_by_category_home_batch,
    parse_batch_slugs,
)
from app.queries.news_common import category_list_item, serialize_news_list
from app.queries.news_sports import news_by_category_sports as _news_by_category_sports
from app.queries.news_worldcup import news_by_category_world_cup as _news_by_category_world_cup

router = APIRouter(tags=["news"])


def not_found(model_name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{model_name}].")


@router.get("/news-details/{slug}")
async def news_details(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(News)
        .where(News.slug_key == slug, News.published.is_(True), News.deleted_at.is_(None))
        .options(
            selectinload(News.news_seo),
            selectinload(News.category),
            selectinload(News.details),
            selectinload(News.tags),
            selectinload(News.authors),
            selectinload(News.news_locations),
            selectinload(News.live_news_row),
            selectinload(News.news_images),
        )
    )
    news = (await db.execute(stmt)).scalars().first()
    if news is None:
        raise not_found("News")

    # Fire-and-forget read tracking (mirrors NewsReadService::read()) — never
    # affects the response even if it fails.
    visitor_id = request.headers.get("X-Visitor-ID")
    if visitor_id:
        try:
            insert_stmt = (
                pg_insert(NewsRead)
                .values(
                    news_id=news.id,
                    category_id=news.category_id,
                    read_date=portal_time.today_date_string(),
                    visitor_id=visitor_id,
                    read_count=1,
                )
                .on_conflict_do_nothing()
            )
            await db.execute(insert_stmt)
            await db.commit()
        except Exception:
            await db.rollback()

    category_item = await category_list_item(db, news.category) if news.category else None
    news_url = f"/{category_item.path}/{news.slug_key}" if category_item else f"/{news.slug_key}"

    reporter_field = None
    # Reporter-portal fields are intentionally out of scope for this port — the
    # source resource conditionally includes `reporter` only when a reporter
    # authored the story; since Reporter models aren't ported here, this stays
    # `None` (equivalent to "no reporter" in every non-reporter-authored story).

    live_news_main_content = None
    if news.live_news_row is not None:
        live_news_main_content = {
            "title": news.live_news_row.title,
            "content": news.live_news_row.content,
            "stopped_at": news.live_news_row.stopped_at.isoformat() if news.live_news_row.stopped_at else None,
            "is_active": news.live_news_row.is_active,
        }

    details = None
    if news.details is not None:
        details = {
            "description": news.details.details,
            "keyword": news.details.keyword,
            "video_link": news.details.video_link,
            "video_source": news.details.video_source,
            "video_iframe": news.details.video_iframe,
            "is_video_in_thumbnail": news.details.is_video_in_thumbnail,
            "google_drive_link": news.details.google_drive_link,
            "audio_link": news.details.audio_link,
        }

    news_seo = news.news_seo
    seo_meta = make_seo(
        title=(news_seo.title if news_seo and news_seo.title else news.title),
        image=(news_seo.og_image if news_seo and news_seo.og_image else get_media_url(news.image)),
        description=(news_seo.description if news_seo and news_seo.description else news.sort_description),
        keywords=(news_seo.keywords if news_seo and news_seo.keywords else [t.name for t in news.tags]),
    )

    news_details_payload = {
        "slug": news.slug_key,
        "url": news_url,
        "title": news.title,
        "ticker": news.ticker,
        "image": get_media_url(news.image),
        "image_caption": news.image_caption,
        "representative": news.representative,
        "is_show_reporter": news.is_show_reporter.value if news.is_show_reporter else None,
        "reporter": reporter_field,
        "shoulder": news.shoulder,
        "sort_description": news.sort_description,
        "live_news": news.live_news,
        "is_thread": news.is_thread,
        "live_news_main_content": live_news_main_content,
        "is_visible_shoulder": news.is_visible_shoulder,
        "is_visible_ticker": news.is_visible_ticker,
        "date": (news.date or news.created_at).isoformat() if (news.date or news.created_at) else None,
        "created_at": news.created_at.isoformat() if news.created_at else None,
        "updated_at": news.updated_at.isoformat() if news.updated_at else None,
        "details": details,
        "authors": [
            {"id": a.id, "name": a.name, "english_name": a.english_name, "slug": a.slug,
             "designation": a.designation, "image": get_media_url(a.image)}
            for a in news.authors
        ],
        "category": category_item.model_dump(mode="json") if category_item else None,
        "tags": [{"name": t.name, "slug": t.slug} for t in news.tags],
        "news_images": [
            {"image_path": get_media_url(i.image_path), "caption": i.caption} for i in news.news_images
        ],
        "seo_meta": seo_meta,
    }

    return {
        "news_details": news_details_payload,
        "latest_news": await latest_news(db),
        "most_read_news": await most_read_news(db),
        "linked_news": await linked_news(db, news.id),
        "news_timelines": await news_timelines(db, news.id),
    }


@router.get("/news-by-category-home-batch")
async def news_by_category_home_batch_route(request: Request, db: AsyncSession = Depends(get_db)):
    raw_comma = request.query_params.get("slugs")
    raw_array = request.query_params.getlist("slugs[]") or None
    slugs = parse_batch_slugs(raw_comma, raw_array)
    return await news_by_category_home_batch(db, slugs)


@router.get("/news-by-category-home/{slug}")
async def news_by_category_home_route(slug: str, db: AsyncSession = Depends(get_db)):
    try:
        return await news_by_category_home(db, slug)
    except NoResultFound:
        raise not_found("Category")


@router.get("/news-by-category/{slug}")
async def news_by_category(
    slug: str,
    request: Request,
    division: str | None = None,
    district: str | None = None,
    upazila: str | None = None,
    date: str | None = None,
    cursor: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        category = await resolve_visible_category(db, slug)
    except NoResultFound:
        raise not_found("Category")

    category_ids = await category_ids_for_slug(db, slug)
    stmt = base_news_query(category_ids)
    stmt = await apply_geo_filter(db, stmt, division, district, upazila)
    stmt = apply_date_filter(stmt, date)

    if cursor:
        # Infinite-scroll page: bypass the "first 3 = lead" split entirely and
        # just keyset-paginate the base query directly (mirrors `$load(true)`).
        page, next_cursor = await keyset_paginate(db, stmt, News.date, News.id, 12, cursor)
        items = [i.model_dump(mode="json") for i in await serialize_news_list(db, page)]
        return cursor_page_envelope(items, next_cursor, 12, f"/api/news-by-category/{slug}")

    lead_news, news_page, next_cursor = await paginate_after_leads(db, stmt, None)
    return await build_full_listing_payload(db, category, lead_news, news_page, next_cursor)


@router.get("/news-by-category-sports")
async def news_by_category_sports_route(cursor: str | None = None, db: AsyncSession = Depends(get_db)):
    try:
        return await _news_by_category_sports(db, cursor)
    except NoResultFound:
        raise not_found("Category")


@router.get("/news-by-category-world-cup")
async def news_by_category_world_cup_route(db: AsyncSession = Depends(get_db)):
    try:
        return await _news_by_category_world_cup(db)
    except NoResultFound:
        raise not_found("Category")


@router.get("/news-by-category-print")
async def news_by_category_print(date: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Category)
        .where(Category.slug == "print", Category.visible.is_(True))
        .options(selectinload(Category.children), selectinload(Category.parent))
    )
    category = (await db.execute(stmt)).scalars().first()
    if category is None:
        raise not_found("Category")

    if date:
        try:
            selected_date = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            selected_date = datetime.utcnow().date()
    else:
        selected_date = datetime.utcnow().date()

    maps_stmt = (
        select(PageCategoryMap)
        .where(PageCategoryMap.date == selected_date)
        .options(selectinload(PageCategoryMap.category))
        .order_by(PageCategoryMap.position)
    )
    maps = (await db.execute(maps_stmt)).scalars().all()

    page_category = []
    for m in maps:
        cat = m.category
        news_stmt = (
            select(News)
            .where(News.category_id == cat.id, News.date == selected_date, News.deleted_at.is_(None))
            .options(selectinload(News.category))
            .limit(5)
        )
        news_rows = (await db.execute(news_stmt)).scalars().all()
        page_category.append({
            "category": {"name": cat.name, "slug": cat.slug, "path": f"/print/{cat.slug}"},
            "news": [i.model_dump(mode="json") for i in await serialize_news_list(db, news_rows)],
        })

    return {
        "category": (await category_list_item(db, category)).model_dump(mode="json"),
        "page_category": page_category,
        "most_read_news": await most_read_news_by_category(db, category.id, 5),
    }


@router.get("/news-by-print-category/{slug}")
async def news_by_print_category(
    slug: str, date: str | None = None, cursor: str | None = None, db: AsyncSession = Depends(get_db)
):
    try:
        category = await resolve_visible_category(db, slug)
    except NoResultFound:
        raise not_found("Category")

    parsed_date = None
    if date:
        # Mirrors newsByPrintCategory(): NOT wrapped in try/except in the source
        # (unlike newsByCategoryPrint) — an unparseable non-empty date raises here too.
        parsed_date = datetime.strptime(date, "%Y-%m-%d").date().isoformat()

    category_ids = await category_ids_for_slug(db, slug)
    stmt = base_news_query(category_ids)
    stmt = apply_date_filter(stmt, parsed_date)

    if cursor:
        page, next_cursor = await keyset_paginate(db, stmt, News.date, News.id, 12, cursor)
        items = [i.model_dump(mode="json") for i in await serialize_news_list(db, page)]
        return cursor_page_envelope(items, next_cursor, 12, f"/api/news-by-print-category/{slug}")

    lead_news, news_page, next_cursor = await paginate_after_leads(db, stmt, None)
    print_edition_children = (
        await categories_ordered_for_print_edition(db, parsed_date) if parsed_date else None
    )
    return await build_full_listing_payload(
        db, category, lead_news, news_page, next_cursor, print_edition_children=print_edition_children
    )


@router.get("/latest-news")
async def latest_news_route(cursor: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(News).where(News.published.is_(True), News.deleted_at.is_(None)).options(
        selectinload(News.category)
    )
    page, next_cursor = await keyset_paginate(db, stmt, News.date, News.id, 20, cursor)
    items = [i.model_dump(mode="json") for i in await serialize_news_list(db, page)]
    return cursor_page_envelope(items, next_cursor, 20, "/api/latest-news")


@router.get("/search")
@limiter.limit(SEARCH)
async def search_news(request: Request, response: Response, query: str = "", page: int = 1, db: AsyncSession = Depends(get_db)):
    query = (query or "").strip()
    if not query:
        return []

    per_page = 20
    like = f"%{query}%"
    base_stmt = (
        select(News)
        .where(
            News.published.is_(True),
            News.deleted_at.is_(None),
            (News.title.ilike(like) | News.sort_description.ilike(like) | News.shoulder.ilike(like)),
        )
        .options(selectinload(News.category))
    )
    total = (await db.execute(select(func.count()).select_from(base_stmt.subquery()))).scalar_one()
    stmt = base_stmt.order_by(News.date.desc(), News.id.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).scalars().all()
    items = [i.model_dump(mode="json") for i in await serialize_news_list(db, rows)]
    last_page = max(1, (total + per_page - 1) // per_page)
    return {
        "data": items,
        "links": {
            "first": f"/api/search?query={query}&page=1",
            "last": f"/api/search?query={query}&page={last_page}",
            "prev": f"/api/search?query={query}&page={page - 1}" if page > 1 else None,
            "next": f"/api/search?query={query}&page={page + 1}" if page < last_page else None,
        },
        "meta": {
            "current_page": page, "from": (page - 1) * per_page + 1 if items else None,
            "last_page": last_page, "path": "/api/search", "per_page": per_page,
            "to": (page - 1) * per_page + len(items) if items else None, "total": total,
        },
    }


@router.get("/news-by-tags/{name}")
async def news_by_tags(name: str, request: Request, cursor: str | None = None, db: AsyncSession = Depends(get_db)):
    tag = (await db.execute(select(Tag).where(Tag.slug == name))).scalars().first()
    if tag is None:
        raise not_found("Tag")

    stmt = (
        select(News)
        .join(News.tags)
        .where(Tag.slug == name, News.published.is_(True), News.deleted_at.is_(None))
        .options(selectinload(News.category))
    )
    page, next_cursor = await keyset_paginate(db, stmt, News.created_at, News.id, 20, cursor)
    items = [i.model_dump(mode="json") for i in await serialize_news_list(db, page)]
    envelope = cursor_page_envelope(items, next_cursor, 20, f"/api/news-by-tags/{name}")

    if "cursor" in request.query_params:
        return envelope

    return {
        "seo_meta": make_seo(
            title=tag.title or "", image=tag.og_image or "",
            description=tag.description or "", keywords=tag.keywords or [],
        ),
        "news_list": envelope,
    }


@router.get("/news-by-author/{slug}")
async def news_by_author(slug: str, request: Request, cursor: str | None = None, db: AsyncSession = Depends(get_db)):
    author = (await db.execute(select(Author).where(Author.slug == slug))).scalars().first()
    if author is None:
        raise not_found("Author")

    stmt = (
        select(News)
        .join(News.authors)
        .where(Author.id == author.id, News.published.is_(True), News.deleted_at.is_(None))
        .options(selectinload(News.category))
    )
    page, next_cursor = await keyset_paginate(db, stmt, News.created_at, News.id, 20, cursor)
    items = [i.model_dump(mode="json") for i in await serialize_news_list(db, page)]
    envelope = cursor_page_envelope(items, next_cursor, 20, f"/api/news-by-author/{slug}")

    if "cursor" in request.query_params:
        return envelope

    return {
        "author": {
            "id": author.id, "name": author.name, "english_name": author.english_name,
            "designation": author.designation, "bio": author.bio, "image": get_media_url(author.image),
            "facebook": author.facebook, "email": author.email, "linkedin_url": author.linkedin_url,
        },
        **envelope,
    }
