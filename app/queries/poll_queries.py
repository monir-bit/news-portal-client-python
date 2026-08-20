"""Queries + serialization for App\\Http\\Controllers\\Api\\PollController.

Poll.activeNow() tolerates NULL starts_at/ends_at as "unbounded" — this is
intentionally ASYMMETRIC with Question.activeNow() (see question_queries.py,
which does NOT null-tolerate start_time/end_time), per the source Laravel app.
Do not unify the two scopes.
"""

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import PollPage
from app.models.poll import Poll, PollOption, PollVote


def _active_now_clauses(now: datetime):
    return (
        Poll.is_active.is_(True),
        or_(Poll.starts_at.is_(None), Poll.starts_at <= now),
        or_(Poll.ends_at.is_(None), Poll.ends_at >= now),
    )


async def count_polls(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(Poll))).scalar_one()


async def list_polls(session: AsyncSession, page: int, per_page: int) -> list[Poll]:
    """Mirrors PollController::index — NOT scoped by activeNow(); returns every
    poll regardless of is_active/date window, newest id first."""
    stmt = (
        select(Poll)
        .options(selectinload(Poll.options))
        .order_by(Poll.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_active_poll(session: AsyncSession, poll_id: int) -> Poll | None:
    """Mirrors PollController::show — Poll::activeNow()->whereKey($id)->firstOrFail()."""
    now = datetime.utcnow()
    stmt = (
        select(Poll)
        .where(Poll.id == poll_id, *_active_now_clauses(now))
        .options(selectinload(Poll.options))
    )
    return (await session.execute(stmt)).scalars().first()


async def get_first_active_poll_by_page(session: AsyncSession, page_enum: PollPage) -> Poll | None:
    """Mirrors PollController::firstByPage — oldest (lowest id) currently-active
    poll for the given page."""
    now = datetime.utcnow()
    stmt = (
        select(Poll)
        .where(Poll.page == page_enum, *_active_now_clauses(now))
        .options(selectinload(Poll.options))
        .order_by(Poll.id.asc())
    )
    return (await session.execute(stmt)).scalars().first()


async def poll_option_exists(session: AsyncSession, option_id: int) -> bool:
    """Mirrors PollVoteStoreRequest's `exists:poll_options,id` rule — unscoped,
    checked against the whole poll_options table (poll-scoping happens later)."""
    stmt = select(PollOption.id).where(PollOption.id == option_id)
    return (await session.execute(stmt)).scalars().first() is not None


async def get_option_for_poll(session: AsyncSession, poll_id: int, option_id: int) -> PollOption | None:
    """Mirrors the real scoping check: the option must belong to this exact poll."""
    stmt = select(PollOption).where(PollOption.poll_id == poll_id, PollOption.id == option_id)
    return (await session.execute(stmt)).scalars().first()


async def has_voted(session: AsyncSession, poll_id: int, ip: str) -> bool:
    """Dedup key is (poll_id, ip_address) ONLY — no session/cookie/user check."""
    stmt = select(PollVote.id).where(PollVote.poll_id == poll_id, PollVote.ip_address == ip)
    return (await session.execute(stmt)).scalars().first() is not None


def _page_value(page) -> str:
    return page.value if hasattr(page, "value") else str(page)


async def serialize_poll(session: AsyncSession, poll: Poll, ip: str | None) -> dict:
    """Mirrors PollResource::make($poll)->resolve() / ->toArray() — both produce
    the same field set for this resource (no conditional `when`/`whenLoaded`
    fields), so one helper covers index/show/firstByPage/vote.

    `user_has_voted` is a LIVE per-request DB query keyed off the caller's IP,
    not a stored/cached flag — matches the source exactly, including the N+1
    query-per-row cost on the paginated `index` listing."""
    voted = await has_voted(session, poll.id, ip) if ip else False
    options_sum = sum(o.votes_count for o in poll.options)
    return {
        "id": poll.id,
        "question": poll.question,
        "description": poll.description,
        "page": _page_value(poll.page),
        "is_active": poll.is_active,
        "starts_at": poll.starts_at.isoformat() if poll.starts_at else None,
        "ends_at": poll.ends_at.isoformat() if poll.ends_at else None,
        "options": [
            {"id": o.id, "option_text": o.option_text, "votes_count": o.votes_count}
            for o in poll.options
        ],
        "options_sum_votes_count": int(options_sum),
        "user_has_voted": voted,
    }
