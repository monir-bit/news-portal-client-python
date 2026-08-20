"""Sitemap endpoints — mirrors `App\\Http\\Controllers\\Api\\SitemapController`.

Per explicit user decision this is ported as LIVE endpoints even though the
Laravel source never actually wires this controller to a route (see
app/queries/sitemap_queries.py's module docstring for the full context). Mount
at the router root (no extra prefix) — main.py adds the shared `/api` prefix,
giving final paths `/api/sitemap`, `/api/sitemap/posts`, etc.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.queries import sitemap_queries as queries

router = APIRouter(tags=["sitemap"])

DEFAULT_PER_PAGE = 50000


@router.get("/sitemap")
async def sitemap_index(db: AsyncSession = Depends(get_db)):
    """Mirrors SitemapController::index()."""
    total = await queries.get_posts_total_count(db)
    page_count = queries.get_posts_page_count(total, DEFAULT_PER_PAGE)
    return {
        "sitemaps": {
            "post_pages": page_count,
            "categories": True,
            "tags": True,
            "news_48h": True,
        }
    }


@router.get("/sitemap/posts")
async def sitemap_posts(page: int = 1, per_page: int = DEFAULT_PER_PAGE, db: AsyncSession = Depends(get_db)):
    """Mirrors SitemapController::posts(). Source coerces arbitrary query-string
    input via PHP's `(int)` cast (`max(1, (int) page)` / `min(50000, max(1,
    (int) per_page))`), so a non-numeric value would silently fall back to the
    floor rather than error; here `page`/`per_page` are typed `int` (consistent
    with every other paginated route in this codebase, e.g. /search), so a
    non-integer value 422s instead of silently defaulting — a deliberate,
    minor deviation for consistency with the rest of the port."""
    page = max(1, page)
    per_page = min(50000, max(1, per_page))
    data = await queries.get_posts(db, page, per_page)
    total = await queries.get_posts_total_count(db)
    total_pages = queries.get_posts_page_count(total, per_page)
    return {
        "data": data,
        "meta": {"page": page, "per_page": per_page, "total": total, "total_pages": total_pages},
    }


@router.get("/sitemap/categories")
async def sitemap_categories(db: AsyncSession = Depends(get_db)):
    """Mirrors SitemapController::categories()."""
    return {"data": await queries.get_categories(db)}


@router.get("/sitemap/tags")
async def sitemap_tags(db: AsyncSession = Depends(get_db)):
    """Mirrors SitemapController::tags()."""
    return {"data": await queries.get_tags(db)}


@router.get("/sitemap/news-last-48h")
async def sitemap_news_last_48h(db: AsyncSession = Depends(get_db)):
    """Mirrors SitemapController::newsLast48Hours()."""
    return {"data": await queries.get_news_last_48h(db)}
