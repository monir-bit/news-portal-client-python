"""Queries + serialization for App\\Http\\Controllers\\Api\\WebStoryController.

Caching deferred: the source caches sliderData()/sportsWebHistory() for 10
minutes via `rakibmiah99/agamirsomoy-shared-cache`'s CacheKey helper; no
caching/Redis in this pass per project scope cut (documented in the
implementation guide) — both are served uncached here. `sliderDetails()` was
never cached in the source either, so no TTL is owed there.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.category_tree import self_and_direct_children_ids
from app.core.media import get_media_url
from app.models.news import News
from app.models.webstory import WebStory
from app.queries.news_common import serialize_news_list_item


def _slider_item(story: WebStory) -> dict:
    """Mirrors WebStorySliderDataResource: `{hash_key, image, title}` sourced
    from the FIRST item of the story's `items` relation (relation-level
    `orderBy('position')` — already applied via WebStory.items' relationship
    ordering). `image` is always the resolved media URL: WebStoryItem's
    `getImageAttribute()` overrides the raw column for every read in the
    source, unlike CommentNewsCard's separate raw-column/`image_url`-accessor
    split. `title` falls back to "" (not null) when there are no items, or
    when the first item's own title is null."""
    first_item = story.items[0] if story.items else None
    if first_item is None:
        return {"hash_key": story.hash_key, "image": None, "title": ""}
    return {
        "hash_key": story.hash_key,
        "image": get_media_url(first_item.image),
        "title": first_item.title or "",
    }


async def slider_data(session: AsyncSession) -> list[dict]:
    """Mirrors WebStoryController::sliderData() — NO filter on news.published
    at all (unlike sliderDetails/comment-card, which do filter through
    published/category-recursion)."""
    stmt = (
        select(WebStory)
        .options(selectinload(WebStory.items), selectinload(WebStory.news))
        .order_by(WebStory.created_at.desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_slider_item(w) for w in rows]


async def sports_web_story_slider_data(session: AsyncSession) -> list[dict]:
    """Mirrors WebStoryController::sportsWebHistory(). Category id resolution
    is intentionally shallow — self + DIRECT children of 'sports' only, NOT
    the full subtree (see self_and_direct_children_ids's docstring for why) —
    a real, likely-unintentional limitation in the source that must be
    preserved exactly, not "fixed" into a full recursive walk.

    Query mirrors `News::whereHas('webStory')->whereIn('category_id', ids)
    ->orderByDesc('created_at')->limit(10)->get()->pluck('webStory')` by
    selecting WebStory joined to News and ordering/limiting on News.created_at
    directly (equivalent since News->webStory is a 1:1 hasOne in practice)."""
    category_ids = await self_and_direct_children_ids(session, ["sports"])
    if not category_ids:
        return []
    stmt = (
        select(WebStory)
        .join(WebStory.news)
        .where(News.category_id.in_(category_ids))
        .options(selectinload(WebStory.items))
        .order_by(News.created_at.desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [_slider_item(w) for w in rows]


async def get_web_story_by_hash(session: AsyncSession, hash_key: str) -> WebStory | None:
    """Mirrors WebStoryController::sliderDetails(). The source's `orderBy` +
    `limit(10)` ahead of `where('hash_key', ...)->firstOrFail()` are vestigial
    no-ops given the single-row result — dropped here as a harmless
    simplification (see spec). No `published` filter on the linked news."""
    stmt = (
        select(WebStory)
        .where(WebStory.hash_key == hash_key)
        .options(
            selectinload(WebStory.items),
            selectinload(WebStory.news).selectinload(News.category),
        )
    )
    return (await session.execute(stmt)).scalars().first()


async def serialize_web_story_details(session: AsyncSession, story: WebStory) -> dict:
    """Mirrors the plain associative array returned by sliderDetails(). `items`
    are column-restricted to title/image/web_story_id in the source (`id` is
    NOT selected there and so is omitted here too; `position` is likewise
    absent). `image` is resolved via get_media_url like every WebStoryItem read."""
    items_payload = [
        {"title": i.title, "image": get_media_url(i.image), "web_story_id": i.web_story_id}
        for i in story.items
    ]
    news_payload = None
    if story.news is not None:
        news_item = await serialize_news_list_item(session, story.news)
        news_payload = news_item.model_dump(mode="json")
    return {
        "id": story.id,
        "hash_key": story.hash_key,
        "items": items_payload,
        "news": news_payload,
    }
