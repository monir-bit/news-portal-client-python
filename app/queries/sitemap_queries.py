"""Sitemap query logic — mirrors `App\\Services\\Api\\SitemapService`
(app/Services/Api/SitemapService.php) and the response shapes built by
`App\\Http\\Controllers\\Api\\SitemapController`.

NOTE ON ROUTING (per explicit user decision): `Api\\SitemapController` /
`SitemapService` exist in the Laravel source but are NOT wired to any route
there (confirmed dead code — see scratchpad/specs/misc_public_domain.md
section 4, full repo search of routes/api.php, routes/web.php,
bootstrap/app.php turned up zero references). This FastAPI port exposes them
as live, working endpoints anyway (see app/routers/sitemap.py) — this is
intentionally NEW externally-reachable behavior versus the current Laravel
app, not a bug in the port.

NOTE ON DATE FORMAT: every date field here is formatted like
`Carbon::toIso8601String()` (`Y-m-d\\TH:i:sP`, e.g.
`2026-08-20T10:00:00+06:00`), matching the literal `?->toIso8601String()`
calls described for these service methods — NOT Eloquent's default
`...Z`-suffixed JSON-cast format used elsewhere in this domain (e.g.
StaticPage.updated_at on the /pages route). The spec doc's illustrative JSON
sample for `/sitemap/posts` shows a `...Z` value, but the prose describing the
actual method call (`toIso8601String()`) is authoritative and is what's
implemented here.
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import portal_time
from app.core.category_tree import build_category_path
from app.models.category import Category
from app.models.news import News, news_tag_mappings
from app.models.tag_author import Tag

# SitemapService::getCategories()'s hardcoded static-page tail list, concatenated
# after the real categories and deduped by `url` (categories win on collision
# since they're concatenated first in the source).
STATIC_SITEMAP_ENTRIES: list[dict] = [
    {"slug": "home", "url": "/"},
    {"slug": "latest", "url": "/collection/latest"},
    {"slug": "terms", "url": "/terms"},
    {"slug": "about", "url": "/about"},
    {"slug": "contact", "url": "/contact"},
    {"slug": "privacy", "url": "/privacy"},
    {"slug": "photo", "url": "/photo"},
    {"slug": "video", "url": "/video"},
]


def _iso8601(dt: datetime | None) -> str | None:
    """Mirrors Carbon::toIso8601String(). DB timestamps here are naive Postgres
    `timestamp WITHOUT TIME ZONE` values already holding Asia/Dhaka wall-clock
    time (see app/core/portal_time.py's `_naive()`), so we attach that zone
    for display rather than converting anything."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=portal_time.TIMEZONE)
    return dt.isoformat()


def _published_news_filter():
    # News::where('published', true) — Eloquent's implicit SoftDeletes global
    # scope also excludes trashed rows, so `deleted_at IS NULL` is reproduced
    # explicitly here (same convention as app/routers/news.py).
    return (News.published.is_(True), News.deleted_at.is_(None))


async def build_news_url(db: AsyncSession, category_id: int | None, slug_key: str) -> str:
    """Mirrors SitemapService's private buildNewsUrl()."""
    if category_id is None:
        return f"/{slug_key}"
    path = await build_category_path(db, category_id)
    return f"/{path}/{slug_key}" if path else f"/{slug_key}"


async def get_posts_total_count(db: AsyncSession) -> int:
    stmt = select(func.count()).select_from(News).where(*_published_news_filter())
    return (await db.execute(stmt)).scalar_one()


def get_posts_page_count(total: int, per_page: int) -> int:
    if per_page <= 0:
        return 0
    return (total + per_page - 1) // per_page


async def get_posts(db: AsyncSession, page: int, per_page: int) -> list[dict]:
    page = max(1, page)
    per_page = min(50000, max(1, per_page))
    stmt = (
        select(News)
        .where(*_published_news_filter())
        .order_by(News.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(stmt)).scalars().all()
    result = []
    for n in rows:
        result.append({
            "slug": n.slug_key,
            "url": await build_news_url(db, n.category_id, n.slug_key),
            "lastmod": _iso8601(n.updated_at) or _iso8601(n.created_at),
        })
    return result


async def get_tags(db: AsyncSession) -> list[str]:
    """Mirrors Tag::whereHas('news', fn($q) => $q->where('published', true))
    ->pluck('name')->unique()->values()->all() — distinct names of tags with
    at least one published (and non-soft-deleted) news item attached."""
    stmt = (
        select(Tag.name)
        .join(news_tag_mappings, news_tag_mappings.c.tag_id == Tag.id)
        .join(News, News.id == news_tag_mappings.c.news_id)
        .where(*_published_news_filter())
        .distinct()
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def get_categories(db: AsyncSession) -> list[dict]:
    """Mirrors SitemapService::getCategories(): visible categories mapped to
    {slug, url}, concatenated with the hardcoded static-page list, deduped by
    `url` (first occurrence wins — categories first, so they win any collision)."""
    stmt = select(Category).where(Category.visible.is_(True))
    categories = (await db.execute(stmt)).scalars().all()

    items: list[dict] = []
    seen_urls: set[str] = set()
    for c in categories:
        path = await build_category_path(db, c.id)
        url = f"/{path}" if path else "/"
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append({"slug": c.slug, "url": url})

    for entry in STATIC_SITEMAP_ENTRIES:
        if entry["url"] in seen_urls:
            continue
        seen_urls.add(entry["url"])
        items.append(entry)

    return items


async def get_news_last_48h(db: AsyncSession) -> list[dict]:
    """Mirrors SitemapService::getNewsLast48Hours(): published news created in
    the last rolling 48h window, newest first."""
    cutoff = portal_time.now() - timedelta(hours=48)
    stmt = (
        select(News)
        .where(*_published_news_filter(), News.created_at >= cutoff)
        .order_by(News.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    result = []
    for n in rows:
        result.append({
            "slug": n.slug_key,
            "url": await build_news_url(db, n.category_id, n.slug_key),
            "title": n.title,
            "date": _iso8601(n.created_at),
        })
    return result
