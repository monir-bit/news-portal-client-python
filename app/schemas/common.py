"""Shared response shapes reused across almost every router — mirrors
NewsListResource / CategoryListResource, the two most-reused Laravel resources."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CategoryBrief(BaseModel):
    """`{name, slug}` only — used by news-by-category-home(-batch), no `path` key."""

    name: str
    slug: str


class CategoryListItem(BaseModel):
    """Mirrors CategoryListResource: `{name, slug, path}`."""

    name: str
    slug: str
    path: str


class LiveNewsBrief(BaseModel):
    id: int
    news_id: int
    is_active: bool


class NewsListItem(BaseModel):
    """Mirrors NewsListResource. `category`/`live_news` are only populated when
    the caller actually eager-loaded them (mirrors Laravel's whenLoaded/whenLoaded
    semantics) — both are Optional and simply omitted (None) otherwise."""

    id: int
    category_id: int
    slug_key: str
    title: str
    ticker: str | None
    image: str | None
    image_caption: str | None
    shoulder: str | None
    sort_description: str
    live_news: bool
    is_thread: bool
    is_visible_shoulder: bool
    is_visible_ticker: bool
    date: datetime
    created_at: datetime | None
    representative: str | None
    url: str
    category: CategoryListItem | None = None
    live_news_data: LiveNewsBrief | None = None


class Pagination(BaseModel):
    """Generic envelope for the hand-rolled cursor-pagination shapes used by
    CategoryNewsPageService::buildFullListingPayload (NOT Laravel's automatic
    cursor-paginator shape, which is emitted as a raw dict in a few endpoints
    that return the paginator object directly instead)."""

    data: list[Any]
    links: dict[str, str | None]
    meta: dict[str, str | None]
