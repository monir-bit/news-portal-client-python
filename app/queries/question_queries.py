"""Queries + serialization for App\\Http\\Controllers\\Api\\QuestionController.

Question.activeNow() does NOT tolerate NULL start_time/end_time the way
Poll.activeNow() tolerates NULL starts_at/ends_at (see poll_queries.py) — a
plain `start_time <= now AND end_time >= now` naturally excludes NULL rows at
the SQL level (comparisons against NULL are unknown, i.e. filtered out by
WHERE), which is exactly the source's (probably-unintentional) behavior. Do
NOT add an `IS NULL` fallback here — that would change which questions are
ever considered "active".

Participant dedup for question answers is by `(question_id, participant_id)`,
where `participant_id` is resolved via a PHONE-ONLY lookup/create — no IP
involved anywhere in this domain (contrast with Poll's IP-based dedup).
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import Category
from app.models.participant import Participant
from app.models.question import Question, QuestionAnswer, QuestionOption


async def find_category_by_slug(session: AsyncSession, slug: str) -> Category | None:
    """Plain existence lookup — no activeNow filter at the category level."""
    stmt = select(Category).where(Category.slug == slug)
    return (await session.execute(stmt)).scalars().first()


def _active_now_clauses(now: datetime):
    return (
        Question.is_active.is_(True),
        Question.start_time <= now,
        Question.end_time >= now,
    )


async def first_active_question_for_category(session: AsyncSession, category_id: int) -> Question | None:
    """Mirrors QuestionController::getQuestion()'s `$category->questions->first()`
    over the activeNow-filtered eager load. The source has no explicit ORDER BY;
    ordering by id here gives a stable, deterministic pick matching the source's
    "arbitrary-ish, effectively lowest id in practice" note."""
    now = datetime.utcnow()
    stmt = (
        select(Question)
        .where(Question.category_id == category_id, *_active_now_clauses(now))
        .options(selectinload(Question.options))
        .order_by(Question.id)
    )
    return (await session.execute(stmt)).scalars().first()


async def get_active_question(session: AsyncSession, category_id: int, question_id: int) -> Question | None:
    """Mirrors `Question::where('category_id', ...)->activeNow()->where('id', ...)`,
    used by both `participation` and `submitAnswer` (each wraps the None result
    differently — see the router)."""
    now = datetime.utcnow()
    stmt = select(Question).where(
        Question.category_id == category_id,
        Question.id == question_id,
        *_active_now_clauses(now),
    )
    return (await session.execute(stmt)).scalars().first()


async def question_exists(session: AsyncSession, question_id: int) -> bool:
    """Mirrors the unscoped `exists:questions,id` validation rule."""
    stmt = select(Question.id).where(Question.id == question_id)
    return (await session.execute(stmt)).scalars().first() is not None


async def question_option_exists(session: AsyncSession, option_id: int) -> bool:
    """Mirrors the unscoped `exists:question_options,id` validation rule."""
    stmt = select(QuestionOption.id).where(QuestionOption.id == option_id)
    return (await session.execute(stmt)).scalars().first() is not None


async def get_option_for_question(
    session: AsyncSession, question_id: int, option_id: int
) -> QuestionOption | None:
    """Scoped check: the option must belong to this exact question."""
    stmt = select(QuestionOption).where(
        QuestionOption.question_id == question_id, QuestionOption.id == option_id
    )
    return (await session.execute(stmt)).scalars().first()


async def get_participant_by_phone(session: AsyncSession, phone: str) -> Participant | None:
    """Participant identity is phone-only (unique constraint) — matches every
    `Participant::where('phone', ...)` lookup in the source across this domain."""
    stmt = select(Participant).where(Participant.phone == phone)
    return (await session.execute(stmt)).scalars().first()


async def get_or_create_participant(
    session: AsyncSession,
    phone: str,
    name: str,
    email: str | None,
    existing: Participant | None = None,
) -> Participant:
    """Mirrors `Participant::firstOrCreate(['phone' => ...], ['name' => ..., 'email' => ...])`.
    Match key is phone ONLY — if a participant with this phone already exists,
    their name/email are NEVER overwritten even if the request supplies
    different values. Pass an already-fetched row via `existing` (the caller
    needs it anyway for the "name required for new phone" validation) to avoid
    a redundant query."""
    participant = existing if existing is not None else await get_participant_by_phone(session, phone)
    if participant is not None:
        return participant
    participant = Participant(phone=phone, name=name, email=email)
    session.add(participant)
    await session.flush()
    return participant


async def has_answered(session: AsyncSession, question_id: int, participant_id: int) -> bool:
    """Dedup key is (question_id, participant_id) — no IP/session involved."""
    stmt = select(QuestionAnswer.id).where(
        QuestionAnswer.question_id == question_id, QuestionAnswer.participant_id == participant_id
    )
    return (await session.execute(stmt)).scalars().first() is not None


def serialize_question(question: Question) -> dict:
    """Mirrors QuestionResource. QuestionOptionResource never exposes
    `is_correct` — correctness is never leaked to this public endpoint."""
    return {
        "id": question.id,
        "title": question.title,
        "description": question.description,
        "options": [
            {"id": o.id, "question_id": o.question_id, "option_text": o.option_text}
            for o in question.options
        ],
    }
