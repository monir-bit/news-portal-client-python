import re

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.layout import LayoutSection, LayoutSectionNews
from app.models.news import News
from app.queries.news_common import serialize_news_list

SLUG_RE = re.compile(r"^[a-z0-9\-]+$")


async def news_by_category_home(session: AsyncSession, slug: str) -> dict:
    """Mirrors NewsController::cachedNewsByCategoryHome($slug) (shared by both
    /news-by-category-home/{slug} and /news-by-category-home-batch).
    Raises NoResultFound (-> 404) if the category doesn't exist/isn't visible."""
    category = (
        await session.execute(
            select(Category)
            .where(Category.slug == slug, Category.visible.is_(True))
            .options(selectinload(Category.children))
        )
    ).scalars().one()

    excluded_stmt = (
        select(LayoutSectionNews.news_id)
        .join(LayoutSection, LayoutSection.id == LayoutSectionNews.layout_section_id)
        .where(LayoutSection.is_enable.is_(True), LayoutSectionNews.position <= LayoutSection.max_news)
    )
    excluded_ids = [row[0] for row in (await session.execute(excluded_stmt)).fetchall()]

    stmt = select(News).where(News.published.is_(True), News.deleted_at.is_(None))
    if excluded_ids:
        stmt = stmt.where(News.id.notin_(excluded_ids))

    if category.parent_id:
        stmt = stmt.where(News.category_id == category.id)
    else:
        child_ids = [c.id for c in category.children] + [category.id]
        stmt = stmt.where(News.category_id.in_(child_ids))

    stmt = stmt.options(selectinload(News.category)).order_by(News.date.desc()).limit(15)
    rows = (await session.execute(stmt)).scalars().all()

    return {
        "category": {"name": category.name, "slug": category.slug},
        "news": [i.model_dump(mode="json") for i in await serialize_news_list(session, rows)],
    }


async def news_by_category_home_batch(session: AsyncSession, slugs: list[str]) -> dict:
    """Mirrors newsByCategoryHomeBatch(): hard cap of 24 slugs (applied by the
    caller before this function runs), regex-valid slugs only, unknown/invisible
    categories map to `None` rather than raising."""
    result: dict = {}
    for slug in slugs:
        if not SLUG_RE.match(slug):
            continue
        try:
            result[slug] = await news_by_category_home(session, slug)
        except NoResultFound:
            result[slug] = None
    return result


def parse_batch_slugs(raw_comma: str | None, raw_array: list[str] | None) -> list[str]:
    """Mirrors the dual string/array query-param parsing in
    NewsController::newsByCategoryHomeBatch(), including the "string branch
    doesn't dedupe, array branch does" asymmetry — then always caps at 24."""
    if raw_array:
        seen: list[str] = []
        for s in raw_array:
            s = s.strip()
            if s and s not in seen:
                seen.append(s)
        slugs = seen
    elif raw_comma:
        slugs = [s.strip() for s in raw_comma.split(",") if s.strip()]
    else:
        slugs = []
    return slugs[:24]
