from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.phone import normalize_phone
from app.core.rate_limit import VOTES, limiter
from app.models.question import QuestionAnswer
from app.queries.question_queries import (
    find_category_by_slug,
    first_active_question_for_category,
    get_active_question,
    get_option_for_question,
    get_or_create_participant,
    get_participant_by_phone,
    has_answered,
    question_exists,
    question_option_exists,
    serialize_question,
)

router = APIRouter(tags=["question"])


def _not_found(model_name: str) -> HTTPException:
    """Mirrors Laravel's default ModelNotFoundException JSON body. Kept
    consistent with this port's established convention (see app/routers/news.py)
    of using FastAPI's `detail` key rather than reproducing `{"message": ...}`
    verbatim."""
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{model_name}].")


def _validation_error(errors: dict[str, list[str]]) -> JSONResponse:
    """Mirrors the shape of Laravel's default 422 FormRequest-validation-failure
    body (`{"message": ..., "errors": {...}}`). Unlike a real Laravel
    FormRequest, this fails fast on the first invalid field rather than
    aggregating every field's errors in one pass — a pragmatic simplification;
    the exact multi-field-aggregation behavior isn't otherwise observable by a
    well-behaved client."""
    return JSONResponse(status_code=422, content={"message": "The given data was invalid.", "errors": errors})


class QuestionAnswerBody(BaseModel):
    question_id: int
    question_option_id: int
    phone: str
    name: str | None = None
    email: str | None = None


@router.get("/question/{category_slug}")
async def get_question(category_slug: str, db: AsyncSession = Depends(get_db)):
    """Mirrors QuestionController::getQuestion. Whether the category itself is
    missing, or exists but has zero currently-active questions, both surface
    as the SAME 404 for `App\\Models\\Category` (the source's `whereHas`+
    `firstOrFail()` fails as a single unit for either reason) — never a
    Question-shaped 404."""
    category = await find_category_by_slug(db, category_slug)
    question = await first_active_question_for_category(db, category.id) if category is not None else None
    if category is None or question is None:
        raise _not_found("Category")
    return serialize_question(question)


@router.get("/question/{category_slug}/participation")
async def participation(
    category_slug: str, question_id: int, phone: str, db: AsyncSession = Depends(get_db)
):
    """Mirrors QuestionController::participation. Pure read/check — never
    writes anything. Note the distinct not-found/absent shapes here, none of
    which are the plain ModelNotFoundException shape used by submitAnswer for
    the analogous "question not active" case:
    - unknown category slug -> 404 ModelNotFoundException (Category)
    - question not active/not in category -> 404 with custom body `{"already_answered": false}`
    - no participant yet for that phone -> 200 `{"already_answered": false}`
    - participant + question both exist -> 200 `{"already_answered": <bool>}`
    """
    normalized_phone = normalize_phone(phone)
    if not (10 <= len(normalized_phone) <= 20):
        return _validation_error({"phone": ["The phone field must be between 10 and 20 characters."]})
    if not await question_exists(db, question_id):
        return _validation_error({"question_id": ["The selected question id is invalid."]})

    category = await find_category_by_slug(db, category_slug)
    if category is None:
        raise _not_found("Category")

    question = await get_active_question(db, category.id, question_id)
    if question is None:
        # Deliberate custom 404 body (NOT the framework's ModelNotFoundException
        # shape) — distinguishable from submitAnswer's 404 for the same
        # "question not active in this category" condition.
        return JSONResponse(status_code=404, content={"already_answered": False})

    participant = await get_participant_by_phone(db, normalized_phone)
    if participant is None:
        return {"already_answered": False}

    answered = await has_answered(db, question.id, participant.id)
    return {"already_answered": answered}


@router.post("/question/{category_slug}/answer")
@limiter.limit(VOTES)
async def submit_answer(
    category_slug: str,
    body: QuestionAnswerBody,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Mirrors QuestionController::submitAnswer. Dedup key is
    (question_id, participant_id), where participant_id is resolved via a
    PHONE-ONLY lookup/create — no IP involved at all (contrast with Poll's
    IP-based dedup in poll.py)."""
    normalized_phone = normalize_phone(body.phone)
    if not (10 <= len(normalized_phone) <= 20):
        return _validation_error({"phone": ["The phone field must be between 10 and 20 characters."]})

    if not await question_exists(db, body.question_id):
        return _validation_error({"question_id": ["The selected question id is invalid."]})
    if not await question_option_exists(db, body.question_option_id):
        return _validation_error({"question_option_id": ["The selected question option id is invalid."]})

    # "name" is conditionally required: only for a brand-new phone number.
    # This mirrors QuestionAnswerStoreRequest::rules()'s live DB lookup, run as
    # part of building the validation rules themselves, before "real"
    # validation — replicated here as an early existence check.
    existing_participant = await get_participant_by_phone(db, normalized_phone)
    name = (body.name or "").strip()
    if existing_participant is None and not name:
        return _validation_error({"name": ["Name is required for new participants."]})

    email = (body.email or "").strip() or None
    if email and (len(email) > 99 or "@" not in email):
        return _validation_error({"email": ["The email field must be a valid email address."]})

    category = await find_category_by_slug(db, category_slug)
    if category is None:
        raise _not_found("Category")

    question = await get_active_question(db, category.id, body.question_id)
    if question is None:
        # Framework-default ModelNotFoundException shape here — INCONSISTENT
        # with `participation`'s custom `{"already_answered": false}` 404 for
        # the same underlying condition; this asymmetry is real in the source
        # (submitAnswer uses firstOrFail(), participation doesn't) and is
        # preserved deliberately, not a bug in this port.
        raise _not_found("Question")

    option = await get_option_for_question(db, question.id, body.question_option_id)
    if option is None:
        raise _not_found("QuestionOption")

    try:
        participant = await get_or_create_participant(
            db, normalized_phone, name, email, existing=existing_participant
        )

        if await has_answered(db, question.id, participant.id):
            await db.rollback()
            return JSONResponse(
                status_code=422, content={"message": "Already answered.", "already_answered": True}
            )

        db.add(
            QuestionAnswer(
                question_id=question.id,
                participant_id=participant.id,
                question_option_id=option.id,
                is_correct=bool(option.is_correct),
                answered_at=datetime.utcnow(),
            )
        )
        await db.commit()
    except IntegrityError:
        # Fix vs. source: the DB's hard unique constraint on
        # question_answers(question_id, participant_id) — or, for a brand-new
        # phone submitted twice in the same instant, participants.phone's own
        # unique constraint — is the real backstop for the exists()-check-
        # then-insert race above. The PHP source does NOT catch this and lets
        # it surface as an uncaught 500. Per project decision, translate it to
        # the SAME friendly 422 the app-level check produces.
        await db.rollback()
        return JSONResponse(status_code=422, content={"message": "Already answered.", "already_answered": True})

    return JSONResponse(status_code=201, content={"message": "Submitted.", "already_answered": False})
