"""Port of `App\\Http\\Controllers\\Api\\ElectionController`."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.queries.election_queries import handle_filtered, handle_party_wise, php_truthy_str

router = APIRouter(tags=["election"])


@router.get("/election/results")
async def election_results(
    slug: str | None = None,
    party_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    filters: dict = {}
    if php_truthy_str(slug):
        filters["slug"] = slug
    if php_truthy_str(party_id):
        # Mirrors `(int) $partyId` — a non-numeric party_id casts to 0, which
        # `handleFiltered()`'s `!empty($filters['party_id'])` guard then drops
        # silently (net effect: invalid/non-numeric party_id is ignored, not
        # a 422 — this is the documented source behavior, not a bug).
        try:
            pid = int(party_id)
        except ValueError:
            pid = 0
        if pid:
            filters["party_id"] = pid

    return {"results": await handle_filtered(db, filters)}


@router.get("/election/summary")
async def election_summary(db: AsyncSession = Depends(get_db)):
    return await handle_party_wise(db)
