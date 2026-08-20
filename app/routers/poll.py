from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import PollPage
from app.core.rate_limit import VOTES, limiter
from app.models.poll import PollOption, PollVote
from app.queries.poll_queries import (
    count_polls,
    get_active_poll,
    get_first_active_poll_by_page,
    get_option_for_poll,
    has_voted,
    list_polls,
    poll_option_exists,
    serialize_poll,
)

router = APIRouter(tags=["poll"])


def _not_found(model_name: str) -> HTTPException:
    """Mirrors Laravel's default ModelNotFoundException JSON body for
    firstOrFail()/whereKey() misses. This port's established convention (see
    app/routers/news.py) uses FastAPI's `detail` key rather than reproducing
    Laravel's literal `{"message": ...}` shape verbatim — kept consistent with
    every other router already built in this port."""
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{model_name}].")


class PollVoteBody(BaseModel):
    poll_option_id: int


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/polls")
async def index(request: Request, per_page: int = 30, page: int = 1, db: AsyncSession = Depends(get_db)):
    """Mirrors PollController::index — NOT scoped by activeNow(); returns all
    polls, Laravel's full pagination envelope (data/links/meta)."""
    per_page = min(max(int(per_page), 1), 100)
    page = max(int(page), 1)
    ip = _client_ip(request)

    total = await count_polls(db)
    polls = await list_polls(db, page, per_page)
    data = [await serialize_poll(db, p, ip) for p in polls]

    last_page = max(1, (total + per_page - 1) // per_page)
    base = str(request.url.replace(query=None))

    return {
        "data": data,
        "links": {
            "first": f"{base}?per_page={per_page}&page=1",
            "last": f"{base}?per_page={per_page}&page={last_page}",
            "prev": f"{base}?per_page={per_page}&page={page - 1}" if page > 1 else None,
            "next": f"{base}?per_page={per_page}&page={page + 1}" if page < last_page else None,
        },
        "meta": {
            "current_page": page,
            "from": (page - 1) * per_page + 1 if data else None,
            "last_page": last_page,
            "path": base,
            "per_page": per_page,
            "to": (page - 1) * per_page + len(data) if data else None,
            "total": total,
        },
    }


@router.get("/polls/by-page/{page}")
async def first_by_page(page: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Mirrors PollController::firstByPage. Unknown page slug or no currently
    active poll -> Laravel's literal `abort(404)` body `{"message": "Not Found."}`
    (distinct from the ModelNotFoundException shape used elsewhere in this
    domain) — preserved verbatim since it's cheap to do exactly."""
    try:
        page_enum = PollPage(page)
    except ValueError:
        return JSONResponse(status_code=404, content={"message": "Not Found."})

    poll = await get_first_active_poll_by_page(db, page_enum)
    if poll is None:
        return JSONResponse(status_code=404, content={"message": "Not Found."})

    return await serialize_poll(db, poll, _client_ip(request))


@router.get("/polls/{poll_id:int}")
async def show(poll_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    """Mirrors PollController::show. `{poll_id:int}` replicates Laravel's
    `whereNumber('id')` route constraint — a non-numeric id simply never
    matches this route (falls through to a 404, not a 422)."""
    poll = await get_active_poll(db, poll_id)
    if poll is None:
        raise _not_found("Poll")
    return await serialize_poll(db, poll, _client_ip(request))


@router.post("/polls/{poll_id:int}/vote")
@limiter.limit(VOTES)
async def vote(
    poll_id: int,
    body: PollVoteBody,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Mirrors PollController::vote. Dedup key is (poll_id, ip_address) ONLY —
    no session/cookie/user check at all (contrast with Question's phone-based
    dedup in question.py)."""
    if not await poll_option_exists(db, body.poll_option_id):
        # Mirrors PollVoteStoreRequest's unscoped `exists:poll_options,id` rule
        # failing at the validation layer, before the poll is even looked up.
        return JSONResponse(
            status_code=422,
            content={
                "message": "The selected poll option id is invalid.",
                "errors": {"poll_option_id": ["The selected poll option id is invalid."]},
            },
        )

    poll = await get_active_poll(db, poll_id)
    if poll is None:
        raise _not_found("Poll")

    option = await get_option_for_poll(db, poll.id, body.poll_option_id)
    if option is None:
        # Option exists somewhere, but not for THIS poll.
        raise _not_found("PollOption")

    ip = _client_ip(request)
    if not ip:
        return JSONResponse(status_code=422, content={"message": "Unable to determine client address."})

    if await has_voted(db, poll.id, ip):
        return JSONResponse(
            status_code=422,
            content={"message": "You have already voted in this poll.", "already_voted": True},
        )

    user_agent = request.headers.get("user-agent")
    db.add(PollVote(poll_id=poll.id, poll_option_id=option.id, ip_address=ip, user_agent=user_agent))
    try:
        await db.flush()
        await db.execute(
            update(PollOption).where(PollOption.id == option.id).values(votes_count=PollOption.votes_count + 1)
        )
        await db.commit()
    except IntegrityError:
        # Fix vs. source: the DB's hard unique constraint on
        # poll_votes(poll_id, ip_address) is the real backstop for the
        # exists()-check-then-insert race above; the PHP source does NOT catch
        # this and lets it surface as an uncaught 500. Per project decision,
        # translate it to the SAME friendly 422 the app-level check produces.
        await db.rollback()
        return JSONResponse(
            status_code=422,
            content={"message": "You have already voted in this poll.", "already_voted": True},
        )

    await db.refresh(option)
    poll_payload = await serialize_poll(db, poll, ip)
    return JSONResponse(status_code=201, content={"message": "Vote recorded.", "poll": poll_payload})
