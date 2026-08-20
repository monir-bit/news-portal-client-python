"""Port of `App\\Applications\\Queries\\Api\\ElectionResultQuery`.

Only `handleFiltered()` and `handlePartyWise()` are ported — the source class's
`handle()` method is dead code from the two in-scope routes' perspective
(`ElectionController::results()` calls `handleFiltered()`, `::summary()` calls
`handlePartyWise()`; neither calls `handle()`).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.media import get_media_url
from app.models.election import ElectionParty, ElectionResult

ELECTION_TITLE = "ত্রয়োদশ জাতীয় সংসদ নির্বাচন ২০২৬"


def php_truthy_str(value: str | None) -> bool:
    """Mirrors PHP's `if ($value)` truthiness for a query-string value: only
    `null` and `""` and the literal string `"0"` are falsy; every other
    non-empty string (including `"00"`) is truthy. `ElectionController::results()`
    guards both `slug` and `party_id` with plain `if ($x)`, so a query string of
    `slug=0` or `party_id=0` is treated as "not provided" in the source app —
    replicated here bug-for-bug since it's an explicit, deliberate transcription
    call-out in the porting spec, not an accident worth "fixing"."""
    return value is not None and value != "" and value != "0"


async def _serialize_result(result: ElectionResult) -> dict:
    party = result.party
    return {
        "id": result.id,
        "party_id": result.election_party_id,
        "party_slug": party.slug if party else None,
        "seat_name": result.seat.name if result.seat else None,
        "candidate_name": result.candidate_name,
        "party_name": party.name if party else None,
        # `logo_image`/`party_symbol` are Eloquent accessors in the source
        # model (`getSymbolImageAttribute`/`getPartySymbolAttribute`) that pipe
        # the raw storage path through `UtilsHelper::GetMediaUrl()`. Our
        # SQLAlchemy model stores the raw path, so resolve it explicitly here.
        "logo_image": get_media_url(party.symbol_image) if party else None,
        "party_symbol": get_media_url(party.party_symbol) if party else None,
        "votes_received": result.votes_received,
    }


async def handle_filtered(db: AsyncSession, filters: dict) -> list[dict]:
    """filters: {"party_id": int, "slug": str} — both optional."""
    stmt = (
        select(ElectionResult)
        .options(selectinload(ElectionResult.seat), selectinload(ElectionResult.party))
        .order_by(ElectionResult.id)
    )
    if filters.get("party_id"):
        stmt = stmt.where(ElectionResult.election_party_id == filters["party_id"])
    if filters.get("slug"):
        stmt = stmt.join(ElectionParty, ElectionResult.election_party_id == ElectionParty.id).where(
            ElectionParty.slug == filters["slug"]
        )
    results = (await db.execute(stmt)).scalars().all()
    return [await _serialize_result(r) for r in results]


async def handle_party_wise(db: AsyncSession) -> dict:
    # NOTE: the source `handlePartyWise()` calls `ElectionResult::with('party')->get()`
    # with NO `orderBy()` — unlike `handle()`/`handleFiltered()`, which both add
    # `->orderBy('id')`. Intentionally not adding an ORDER BY here to match.
    stmt = select(ElectionResult).options(selectinload(ElectionResult.party))
    results = (await db.execute(stmt)).scalars().all()

    grouped: dict[int, list[ElectionResult]] = {}
    order: list[int] = []
    for r in results:
        if r.election_party_id not in grouped:
            grouped[r.election_party_id] = []
            order.append(r.election_party_id)
        grouped[r.election_party_id].append(r)

    party_wise = []
    for party_id in order:
        rows = grouped[party_id]
        party = rows[0].party
        party_wise.append(
            {
                "party_id": party_id,
                "party_name": party.name if party else "",
                "slug": party.slug if party else "",
                "seat_count": len(rows),
                "logo_image": get_media_url(party.symbol_image) if party else None,
                "party_symbol": get_media_url(party.party_symbol) if party else None,
            }
        )

    return {"election_title": ELECTION_TITLE, "party_wise": party_wise}
