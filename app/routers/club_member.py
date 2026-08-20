"""Club sign-up form endpoints (Gold/Kids/Career) — mirrors
`ClubMemberApiController::store{Gold,Kids,Career}()` plus the 3
`App\\Http\\Requests\\Api\\*ClubMemberApiStoreRequest` FormRequest classes.

CODEBASE GAP (see spec top-of-file note): `App\\Support\\ClubMember\\
ClubMemberImageValidation`, imported by all 3 (and 3 legacy admin) FormRequest
classes, does not exist anywhere in the Laravel repo — as committed, these 3
routes currently 500 in production (`Class ... not found`). Per explicit user
decision, this port reconstructs a real, working equivalent instead of
reproducing the crash: `image` is optional; if present it must decode as a
genuine image, have one of the extensions jpeg/jpg/png/gif/webp/bmp, and be at
most 5120 KB (5 MB) — inferred from the `image.image` / `image.mimes` /
`image.max` message keys still present in the FormRequests' `messages()`
arrays (the rule set itself was never committed anywhere).

Also per explicit user decision: `phone`/`guardian_phone`/`email` uniqueness on
these 3 tables is application-layer only (no DB unique constraint backs it),
so it's checked here with a plain SELECT before insert, same as the source's
`Rule::unique(...)`.
"""

import io
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import PUBLIC_FORMS, limiter
from app.models.club_member import CareerClubMember, GoldClubMember, KidsClubMember

router = APIRouter(tags=["club-member"])

# fastapi-project/uploads — "next to the FastAPI app" per the user's explicit
# decision; there's no real R2/S3 upload layer wired up in this pass, so the
# validated file is just saved to local disk and the relative path (a random
# UUID-based filename, mirroring UtilsHelper::MonthYearWisePath()'s
# `uploads/{Y}/{m}` layout) is stored in the DB `image` column.
UPLOAD_ROOT = Path(__file__).resolve().parents[2] / "uploads"

ALLOWED_IMAGE_EXTENSIONS = {"jpeg", "jpg", "png", "gif", "webp", "bmp"}
MAX_IMAGE_BYTES = 5120 * 1024  # Laravel's `max:5120` file-size rule is in KB

GENDERS = {"male", "female", "others"}


def _blank(value: str | None) -> str | None:
    """Mirrors the FormRequests' prepareForValidation() (empty-string form
    values for nullable fields are treated as "not provided") plus Laravel's
    default TrimStrings middleware (all string input is trimmed)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _label(field: str) -> str:
    return field.replace("_", " ")


def _add(errors: dict[str, list[str]], field: str, message: str) -> None:
    errors.setdefault(field, []).append(message)


def _check_required(errors: dict, field: str, value: str | None, max_len: int) -> str | None:
    value = _blank(value)
    if value is None:
        _add(errors, field, f"The {_label(field)} field is required.")
        return None
    if len(value) > max_len:
        _add(errors, field, f"The {_label(field)} field must not be greater than {max_len} characters.")
    return value


def _check_nullable_string(errors: dict, field: str, value: str | None, max_len: int) -> str | None:
    value = _blank(value)
    if value is not None and len(value) > max_len:
        _add(errors, field, f"The {_label(field)} field must not be greater than {max_len} characters.")
    return value


def _check_age(errors: dict, value: str | None) -> int | None:
    value = _blank(value)
    if value is None:
        return None
    try:
        age = int(value)
    except ValueError:
        _add(errors, "age", "The age field must be an integer.")
        return None
    if age < 1:
        _add(errors, "age", "The age field must be at least 1.")
    if age > 150:
        _add(errors, "age", "The age field must not be greater than 150.")
    return age


def _check_gender(errors: dict, value: str | None) -> str | None:
    value = _blank(value)
    if value is not None and value not in GENDERS:
        _add(errors, "gender", "The selected gender is invalid.")
    return value


def _check_email(errors: dict, field: str, value: str | None, max_len: int) -> str | None:
    value = _blank(value)
    if value is None:
        _add(errors, field, f"The {_label(field)} field is required.")
        return None
    if len(value) > max_len:
        _add(errors, field, f"The {_label(field)} field must not be greater than {max_len} characters.")
    local, _, domain = value.partition("@")
    if not local or "." not in domain.strip(".") or domain.startswith(".") or domain.endswith("."):
        _add(errors, field, f"The {_label(field)} field must be a valid email address.")
    return value


async def _check_unique(errors: dict, db: AsyncSession, model, field: str, value: str | None) -> None:
    if not value:
        return
    stmt = select(getattr(model, "id")).where(getattr(model, field) == value).limit(1)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        _add(errors, field, f"The {_label(field)} has already been taken.")


async def _validate_image(file: UploadFile | None) -> tuple[str | None, list[str]]:
    """Reconstructed `ClubMemberImageValidation::rules()` — see module
    docstring. Returns (stored_relative_path_or_None, list_of_error_messages)."""
    if file is None or not file.filename:
        return None, []
    raw = await file.read()
    if not raw:
        return None, []

    errors: list[str] = []

    # "image" rule — must actually decode as an image, not just look like one
    # by extension/content-type.
    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError):
        errors.append("The image field must be an image.")

    # "mimes:jpeg,jpg,png,gif,webp,bmp"
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        errors.append("The image field must be a file of type: jpeg, jpg, png, gif, webp, bmp.")

    # "max:5120" (kilobytes)
    if len(raw) > MAX_IMAGE_BYTES:
        errors.append("The image field must not be greater than 5120 kilobytes.")

    if errors:
        return None, errors

    now = datetime.now()
    subdir = UPLOAD_ROOT / f"{now:%Y}" / f"{now:%m}"
    subdir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    (subdir / filename).write_bytes(raw)
    return f"uploads/{now:%Y}/{now:%m}/{filename}", []


def _validation_error_response(errors: dict[str, list[str]]) -> JSONResponse:
    # Standard Laravel FormRequest auto-response shape.
    return JSONResponse(
        status_code=422,
        content={"message": "The given data was invalid.", "errors": errors},
    )


@router.post("/club/gold", status_code=201)
@limiter.limit(PUBLIC_FORMS)
async def store_gold_club_member(
    request: Request,
    name: str | None = Form(None),
    age: str | None = Form(None),
    gender: str | None = Form(None),
    profession: str | None = Form(None),
    blood_group: str | None = Form(None),
    hobby: str | None = Form(None),
    address: str | None = Form(None),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    errors: dict[str, list[str]] = {}
    name = _check_required(errors, "name", name, 255)
    age_val = _check_age(errors, age)
    gender_val = _check_gender(errors, gender)
    profession = _check_nullable_string(errors, "profession", profession, 255)
    blood_group = _check_nullable_string(errors, "blood_group", blood_group, 10)
    hobby = _check_nullable_string(errors, "hobby", hobby, 5000)
    address = _check_required(errors, "address", address, 5000)
    phone = _check_required(errors, "phone", phone, 20)
    email = _check_email(errors, "email", email, 255)

    await _check_unique(errors, db, GoldClubMember, "phone", phone)
    await _check_unique(errors, db, GoldClubMember, "email", email)

    image_path, image_errors = await _validate_image(image)
    if image_errors:
        errors["image"] = image_errors

    if errors:
        return _validation_error_response(errors)

    member = GoldClubMember(
        name=name, age=age_val, gender=gender_val, profession=profession,
        blood_group=blood_group, hobby=hobby, address=address, phone=phone,
        email=email, image=image_path,
    )
    db.add(member)
    await db.commit()
    return {"success": True, "message": "Gold club registration submitted successfully."}


@router.post("/club/kids", status_code=201)
@limiter.limit(PUBLIC_FORMS)
async def store_kids_club_member(
    request: Request,
    name: str | None = Form(None),
    age: str | None = Form(None),
    gender: str | None = Form(None),
    school_or_madrasa: str | None = Form(None),
    blood_group: str | None = Form(None),
    hobby: str | None = Form(None),
    address: str | None = Form(None),
    guardian_phone: str | None = Form(None),
    email: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    errors: dict[str, list[str]] = {}
    name = _check_required(errors, "name", name, 255)
    age_val = _check_age(errors, age)
    gender_val = _check_gender(errors, gender)
    school_or_madrasa = _check_nullable_string(errors, "school_or_madrasa", school_or_madrasa, 255)
    blood_group = _check_nullable_string(errors, "blood_group", blood_group, 10)
    hobby = _check_nullable_string(errors, "hobby", hobby, 5000)
    address = _check_required(errors, "address", address, 5000)
    guardian_phone = _check_required(errors, "guardian_phone", guardian_phone, 20)
    email = _check_email(errors, "email", email, 255)

    await _check_unique(errors, db, KidsClubMember, "guardian_phone", guardian_phone)
    await _check_unique(errors, db, KidsClubMember, "email", email)

    image_path, image_errors = await _validate_image(image)
    if image_errors:
        errors["image"] = image_errors

    if errors:
        return _validation_error_response(errors)

    member = KidsClubMember(
        name=name, age=age_val, gender=gender_val, school_or_madrasa=school_or_madrasa,
        blood_group=blood_group, hobby=hobby, address=address, guardian_phone=guardian_phone,
        email=email, image=image_path,
    )
    db.add(member)
    await db.commit()
    return {"success": True, "message": "Kids club registration submitted successfully."}


@router.post("/club/career", status_code=201)
@limiter.limit(PUBLIC_FORMS)
async def store_career_club_member(
    request: Request,
    name: str | None = Form(None),
    age: str | None = Form(None),
    gender: str | None = Form(None),
    educational_qualification: str | None = Form(None),
    preferred_profession: str | None = Form(None),
    work_experience: str | None = Form(None),
    address: str | None = Form(None),
    phone: str | None = Form(None),
    email: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    errors: dict[str, list[str]] = {}
    name = _check_required(errors, "name", name, 255)
    age_val = _check_age(errors, age)
    gender_val = _check_gender(errors, gender)
    educational_qualification = _check_nullable_string(
        errors, "educational_qualification", educational_qualification, 5000
    )
    preferred_profession = _check_nullable_string(errors, "preferred_profession", preferred_profession, 255)
    work_experience = _check_nullable_string(errors, "work_experience", work_experience, 5000)
    address = _check_required(errors, "address", address, 5000)
    phone = _check_required(errors, "phone", phone, 20)
    email = _check_email(errors, "email", email, 255)

    await _check_unique(errors, db, CareerClubMember, "phone", phone)
    await _check_unique(errors, db, CareerClubMember, "email", email)

    image_path, image_errors = await _validate_image(image)
    if image_errors:
        errors["image"] = image_errors

    if errors:
        return _validation_error_response(errors)

    member = CareerClubMember(
        name=name, age=age_val, gender=gender_val,
        educational_qualification=educational_qualification,
        preferred_profession=preferred_profession, work_experience=work_experience,
        address=address, phone=phone, email=email, image=image_path,
    )
    db.add(member)
    await db.commit()
    return {"success": True, "message": "Career club registration submitted successfully."}
