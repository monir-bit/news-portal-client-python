"""Queries + serialization for App\\Http\\Controllers\\Api\\CommentCardController.

CommentNewsCard uses Laravel SoftDeletes, applied automatically as a global
query scope in the source app (every normal Eloquent query implicitly adds
`deleted_at IS NULL`). SQLAlchemy has no equivalent global scope, so EVERY
query in this module explicitly adds `.where(CommentNewsCard.deleted_at.is_(None))`
— do not drop this when adding new queries against this model.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.media import get_media_url
from app.models.misc_content import CommentNewsCard
from app.models.news import News
from app.queries.news_common import serialize_news_list_item


async def summary(session: AsyncSession) -> list[dict]:
    """Mirrors SliderCommentCardQuery::handle():
    `CommentNewsCard::orderBy('created_at','DESC')->limit(10)->get(['id','image'])`.

    Only `id`/`image` are ever selected — `commenter_image` (and therefore the
    `commenter_image_url` accessor) is never fetched by this endpoint, so
    `commenter_image_url` is ALWAYS None here, regardless of the actual DB
    value. No `is_publish`/`news` filter at all — matches the source exactly."""
    stmt = (
        select(CommentNewsCard.id, CommentNewsCard.image)
        .where(CommentNewsCard.deleted_at.is_(None))
        .order_by(CommentNewsCard.created_at.desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {"id": r.id, "image": r.image, "image_url": get_media_url(r.image), "commenter_image_url": None}
        for r in rows
    ]


async def find_card(session: AsyncSession, card_id: int) -> CommentNewsCard | None:
    """Mirrors `CommentNewsCard::find($id)` (SoftDeletes-scoped existence check)."""
    stmt = select(CommentNewsCard).where(CommentNewsCard.id == card_id, CommentNewsCard.deleted_at.is_(None))
    return (await session.execute(stmt)).scalars().first()


async def current_card(session: AsyncSession, card_id: int) -> CommentNewsCard | None:
    """Mirrors the re-query with `whereHas('news', published=true)` — can be
    None even when `find_card` found a row, if the linked news isn't published
    (or the card has no linked news at all)."""
    stmt = (
        select(CommentNewsCard)
        .join(CommentNewsCard.news)
        .where(
            CommentNewsCard.id == card_id,
            CommentNewsCard.deleted_at.is_(None),
            News.published.is_(True),
        )
        .options(selectinload(CommentNewsCard.news).selectinload(News.category))
    )
    return (await session.execute(stmt)).scalars().first()


async def others_cards(session: AsyncSession, exclude_id: int) -> list[CommentNewsCard]:
    """Mirrors the `$others_card` query: linked news published, card created
    within the last 30 days, excludes the current id, ordered by id DESC (NOT
    created_at DESC), no LIMIT (unbounded)."""
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    stmt = (
        select(CommentNewsCard)
        .join(CommentNewsCard.news)
        .where(
            News.published.is_(True),
            CommentNewsCard.deleted_at.is_(None),
            CommentNewsCard.created_at >= thirty_days_ago,
            CommentNewsCard.id != exclude_id,
        )
        .options(selectinload(CommentNewsCard.news).selectinload(News.category))
        .order_by(CommentNewsCard.id.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def serialize_comment_card(session: AsyncSession, card: CommentNewsCard) -> dict:
    """Mirrors CommentCardResource: `{id, image (image_url accessor), news (NewsListResource)}`."""
    news_payload = None
    if card.news is not None:
        news_item = await serialize_news_list_item(session, card.news)
        news_payload = news_item.model_dump(mode="json")
    return {
        "id": card.id,
        "image": get_media_url(card.image),
        "news": news_payload,
    }
