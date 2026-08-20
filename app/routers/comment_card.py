from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.queries.comment_card_queries import (
    current_card,
    find_card,
    others_cards,
    serialize_comment_card,
    summary,
)

router = APIRouter(tags=["comment-card"])


@router.get("/comment-card-summary")
async def comment_card_summary(db: AsyncSession = Depends(get_db)):
    """Mirrors CommentCardController::commentCardSummary() — raw array,
    bypasses CommentCardResource entirely (see comment_card_queries.summary)."""
    return await summary(db)


@router.get("/comment-card/{card_id}")
async def comment_card_details(card_id: str, db: AsyncSession = Depends(get_db)):
    """Mirrors CommentCardController::details($id). No route-level numeric
    constraint in the source; a non-numeric id there fails
    `CommentNewsCard::find()` (returns null) rather than 404ing at the router
    — replicated here by treating a non-int-parseable id the same as "card
    not found": always a 200 with `{current_card: null, others_card: []}`,
    NEVER a 404, matching the source's exact 200-status-with-nulls contract."""
    try:
        cid = int(card_id)
    except ValueError:
        return {"current_card": None, "others_card": []}

    card = await find_card(db, cid)
    if card is None:
        return {"current_card": None, "others_card": []}

    current = await current_card(db, cid)
    current_payload = await serialize_comment_card(db, current) if current is not None else None

    others = await others_cards(db, cid)
    others_payload = [await serialize_comment_card(db, c) for c in others]

    return {"current_card": current_payload, "others_card": others_payload}
