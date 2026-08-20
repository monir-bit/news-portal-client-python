"""Shared News/Category serialization used by almost every router.

Callers MUST eager-load `News.category` (e.g. `selectinload(News.category)`,
and `selectinload(News.live_news_row)` if `include_live_news=True`) before
calling `serialize_news_list_item` — this mirrors Laravel's whenLoaded()
semantics and avoids async lazy-load errors.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.category_tree import build_category_path
from app.core.media import get_media_url
from app.models.category import Category
from app.models.news import News
from app.schemas.common import CategoryListItem, LiveNewsBrief, NewsListItem


async def news_url(session: AsyncSession, category_id: int | None, slug_key: str) -> str:
    """Mirrors UtilsHelper::NewsUrl($category, $slug)."""
    if category_id is None:
        return f"/{slug_key}"
    path = await build_category_path(session, category_id)
    return f"/{path}/{slug_key}" if path else f"/{slug_key}"


async def category_list_item(session: AsyncSession, category: Category) -> CategoryListItem:
    """Mirrors CategoryListResource::make($category)->resolve()."""
    path = await build_category_path(session, category.id)
    return CategoryListItem(name=category.name, slug=category.slug, path=path)


async def serialize_news_list_item(
    session: AsyncSession,
    news: News,
    *,
    include_category: bool = True,
    include_live_news: bool = False,
) -> NewsListItem:
    """Mirrors NewsListResource::make($news)->resolve()."""
    url = await news_url(session, news.category_id, news.slug_key)

    category = None
    if include_category and news.category is not None:
        category = await category_list_item(session, news.category)

    live_news_data = None
    if include_live_news and getattr(news, "live_news_row", None) is not None:
        live_news_data = LiveNewsBrief(
            id=news.live_news_row.id,
            news_id=news.live_news_row.news_id,
            is_active=news.live_news_row.is_active,
        )

    return NewsListItem(
        id=news.id,
        category_id=news.category_id,
        slug_key=news.slug_key,
        title=news.title,
        ticker=news.ticker,
        image=get_media_url(news.image),
        image_caption=news.image_caption,
        shoulder=news.shoulder,
        sort_description=news.sort_description,
        live_news=news.live_news,
        is_thread=news.is_thread,
        is_visible_shoulder=news.is_visible_shoulder,
        is_visible_ticker=news.is_visible_ticker,
        date=news.date,
        created_at=news.created_at,
        representative=news.representative,
        url=url,
        category=category,
        live_news_data=live_news_data,
    )


async def serialize_news_list(
    session: AsyncSession,
    news_rows: list[News],
    *,
    include_category: bool = True,
    include_live_news: bool = False,
) -> list[NewsListItem]:
    return [
        await serialize_news_list_item(
            session, n, include_category=include_category, include_live_news=include_live_news
        )
        for n in news_rows
    ]
