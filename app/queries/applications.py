"""Python port of app/Applications/Queries/Api/*.php — the shared query layer
reused by NewsController/HomeController/CommonController (and, for
CategoryPageLayoutWiseNewsQuery, by the WorldCup/Sports routes too).

IMPORTANT: `News` uses Laravel's SoftDeletes trait, which adds an automatic
`deleted_at IS NULL` global scope to every Eloquent query. SQLAlchemy has no
such automatic scope — every query below filters `News.deleted_at.is_(None)`
explicitly. Don't drop that filter when extending these queries.

Caching: every `Cache::remember`/`Cache::flexible` call in the Laravel source
is noted in a comment but NOT implemented — this pass defers Redis/caching
entirely (plain DB queries), per the project's implementation guide.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import portal_time
from app.core.category_tree import descendant_ids_by_slug, self_and_direct_children_ids
from app.core.media import get_media_url
from app.models.category import Category
from app.models.layout import CategoryPageLayout, CategoryPageLayoutNews, LayoutSection, LayoutSectionNews
from app.models.news import BreakingNews, LatestNews, LinkedNews, MarqueNews, News, NewsRead, NewsTimeline
from app.models.special import SpecialSegment, SpecialSegmentNews
from app.queries.news_common import serialize_news_list, serialize_news_list_item


async def breaking_news(session: AsyncSession) -> list[dict]:
    """Mirrors BreakingNewsQuery::handle(). Cache: 5 min (deferred)."""
    stmt = (
        select(BreakingNews)
        .where(BreakingNews.published.is_(True))
        .options(selectinload(BreakingNews.news).selectinload(News.category))
        .order_by(BreakingNews.position, BreakingNews.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    out = []
    for bn in rows:
        url = None
        if bn.news is not None:
            item = await serialize_news_list_item(session, bn.news, include_category=False)
            url = item.url
        out.append({"title": bn.title, "hash": bn.hash, "url": url})
    return out


async def latest_news(session: AsyncSession, offset: int = 0, limit: int = 15) -> list[dict]:
    """Mirrors LatestNewsQuery::handle(). Only shows TODAY's news (Asia/Dhaka
    calendar day), not "latest across all time". Cache: 3 min (deferred)."""
    stmt = (
        select(News)
        .join(LatestNews, LatestNews.news_id == News.id)
        .where(
            News.published.is_(True),
            News.deleted_at.is_(None),
            News.date >= portal_time.today_start(),
            News.date <= portal_time.today_end(),
        )
        .options(selectinload(News.category))
        .order_by(News.date.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [item.model_dump(mode="json") for item in await serialize_news_list(session, rows)]


async def marque_news(session: AsyncSession) -> list[dict]:
    """Mirrors MarqueNewsQuery::handle(). Cache: 5 min (deferred). Fixed LIMIT 10,
    ordered by news.date desc (NOT by any marque_news position column)."""
    subq = select(MarqueNews.news_id)
    stmt = (
        select(News)
        .where(News.id.in_(subq), News.published.is_(True), News.deleted_at.is_(None))
        .options(selectinload(News.category))
        .order_by(News.date.desc())
        .limit(10)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [item.model_dump(mode="json") for item in await serialize_news_list(session, rows)]


async def most_read_news(session: AsyncSession) -> list[dict]:
    """Mirrors MostReadNewsQuery::handle() — site-wide, rolling 24h window,
    fixed LIMIT 15. `whereIn(id, ...)` result order is NOT preserved by Postgres,
    so we re-sort in Python to match the ranked-id-list order, exactly like the
    PHP source does. Cache: 3 min, key varies daily (deferred)."""
    rank_stmt = (
        select(NewsRead.news_id)
        .join(News, News.id == NewsRead.news_id)
        .where(
            News.published.is_(True),
            News.date >= portal_time.sub_day(),
            News.date <= portal_time.now(),
        )
        .group_by(NewsRead.news_id)
        .order_by(func.count().desc())
        .limit(15)
    )
    ranked_ids = [row[0] for row in (await session.execute(rank_stmt)).fetchall()]
    if not ranked_ids:
        return []
    stmt = (
        select(News)
        .where(News.id.in_(ranked_ids), News.deleted_at.is_(None))
        .options(selectinload(News.category))
    )
    rows = {n.id: n for n in (await session.execute(stmt)).scalars().all()}
    ordered = [rows[i] for i in ranked_ids if i in rows]
    return [item.model_dump(mode="json") for item in await serialize_news_list(session, ordered)]


async def most_read_news_by_category(session: AsyncSession, category_id: int, limit: int = 15) -> list[dict]:
    """Mirrors MostReadNewsByCategoryQuery::handle($category_id, $limit).
    Scoped to the category PLUS its direct children only (not the full
    subtree) — mirrors CategoryIdsByChildRecursiveQuery's shallow semantics.
    Raises if the category doesn't exist (mirrors `Category::findOrFail`).
    Cache: 5 min (deferred)."""
    category = (
        await session.execute(select(Category).where(Category.id == category_id))
    ).scalar_one()  # 404 upstream if this raises NoResultFound — see router
    children_ids = await self_and_direct_children_ids(session, [category.slug])

    rank_stmt = (
        select(NewsRead.news_id)
        .join(News, News.id == NewsRead.news_id)
        .where(
            News.published.is_(True),
            News.date >= portal_time.sub_day(),
            News.date <= portal_time.now(),
            NewsRead.category_id.in_(children_ids),
        )
        .group_by(NewsRead.news_id)
        .order_by(func.count().desc())
        .limit(limit)
    )
    ranked_ids = [row[0] for row in (await session.execute(rank_stmt)).fetchall()]
    if not ranked_ids:
        return []
    stmt = (
        select(News)
        .where(News.id.in_(ranked_ids), News.deleted_at.is_(None))
        .options(selectinload(News.category))
    )
    rows = {n.id: n for n in (await session.execute(stmt)).scalars().all()}
    ordered = [rows[i] for i in ranked_ids if i in rows]
    return [item.model_dump(mode="json") for item in await serialize_news_list(session, ordered)]


async def recursive_category_tree(session: AsyncSession) -> list[dict]:
    """Mirrors RecursiveCategoryQuery::handle() — root, visible categories,
    EXCLUDING the entire 'print' category subtree, each with a fully nested
    `children` tree (unbounded depth). Cache: 1 day (deferred)."""
    print_ids = await descendant_ids_by_slug(session, "print")

    roots_stmt = select(Category).where(Category.parent_id.is_(None), Category.visible.is_(True))
    if print_ids:
        roots_stmt = roots_stmt.where(Category.id.notin_(print_ids))
    roots_stmt = roots_stmt.order_by(Category.position)
    roots = (await session.execute(roots_stmt)).scalars().all()

    async def transform(category: Category, parent_path: str) -> dict:
        path = f"{parent_path}/{category.slug}"
        children_stmt = (
            select(Category)
            .where(Category.parent_id == category.id)
            .order_by(Category.position)
        )
        children = (await session.execute(children_stmt)).scalars().all()
        return {
            "name": category.name,
            "slug": category.slug,
            "path": path,
            "children": [await transform(c, path) for c in children],
        }

    return [await transform(c, "") for c in roots]


async def special_segment_news(session: AsyncSession, limit: int = 13) -> dict:
    """Mirrors SpecialSegmentNewsQuery::handle($limit). Cache: flexible 300/900s
    (deferred), key varies by `limit`."""
    stmt = select(SpecialSegment).where(SpecialSegment.is_active.is_(True)).options(
        selectinload(SpecialSegment.tag)
    )
    segment = (await session.execute(stmt)).scalars().first()
    if segment is None:
        return {
            "is_active": False,
            "info": {"title": None, "desktop_banner_image": None, "mobile_banner_image": None},
            "news": [],
            "tag": None,
        }
    news_stmt = (
        select(News)
        .join(SpecialSegmentNews, SpecialSegmentNews.news_id == News.id)
        .where(SpecialSegmentNews.special_segment_id == segment.id, News.published.is_(True), News.deleted_at.is_(None))
        .options(selectinload(News.category))
        .order_by(SpecialSegmentNews.position)
        .limit(limit)
    )
    rows = (await session.execute(news_stmt)).scalars().all()
    return {
        "is_active": segment.is_active,
        "info": {
            "title": segment.title,
            "desktop_banner_image": get_media_url(segment.desktop_banner_image),
            "mobile_banner_image": get_media_url(segment.mobile_banner_image),
        },
        "news": [item.model_dump(mode="json") for item in await serialize_news_list(session, rows)],
        "tag": {"id": segment.tag.id, "name": segment.tag.name, "slug": segment.tag.slug} if segment.tag else None,
    }


async def thank_news(session: AsyncSession) -> dict:
    """Mirrors ThankNewsQuery::handle(). Cache: flexible 300/900s (deferred),
    deliberately distinct key from layout_section_wise_news('thanks')."""
    section_stmt = select(LayoutSection.id).where(LayoutSection.slug == "thanks")
    section_id = (await session.execute(section_stmt)).scalar_one_or_none()
    if section_id is None:
        return {}
    stmt = (
        select(News)
        .join(LayoutSectionNews, LayoutSectionNews.news_id == News.id)
        .where(
            LayoutSectionNews.layout_section_id == section_id,
            News.deleted_at.is_(None),
            News.published.is_(True),
        )
        .options(selectinload(News.category), selectinload(News.thank_news), selectinload(News.live_news_row))
        .order_by(LayoutSectionNews.position)
        .limit(1)
    )
    news = (await session.execute(stmt)).scalars().first()
    if news is None:
        return {}
    meta = None
    if news.thank_news is not None:
        meta = {
            "id": news.thank_news.id,
            "news_id": news.thank_news.news_id,
            "title": news.thank_news.title,
            "image": get_media_url(news.thank_news.image),
        }
    item = await serialize_news_list_item(session, news, include_live_news=True)
    return {"meta": meta, "news": item.model_dump(mode="json")}


async def layout_section_wise_news(
    session: AsyncSession, section_slug: str, limit: int | None = None
) -> list[dict]:
    """Mirrors LayoutSectionWiseNewsQuery::handle(). Cache: flexible 300/900s
    (deferred), shared key with handle_live_pin for the same section_slug."""
    section_stmt = select(LayoutSection.id).where(LayoutSection.slug == section_slug)
    section_id = (await session.execute(section_stmt)).scalar_one_or_none()
    if section_id is None:
        return []
    stmt = (
        select(News, LayoutSectionNews.position)
        .join(LayoutSectionNews, LayoutSectionNews.news_id == News.id)
        .where(
            LayoutSectionNews.layout_section_id == section_id,
            News.deleted_at.is_(None),
            News.published.is_(True),
        )
        .options(selectinload(News.category), selectinload(News.live_news_row))
        .order_by(LayoutSectionNews.position)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()
    out = []
    for news, position in rows:
        item = await serialize_news_list_item(session, news, include_live_news=True)
        out.append({"position": position, "news": item.model_dump(mode="json")})
    return out


async def layout_section_wise_news_live_pin(
    session: AsyncSession, section_slug: str, limit: int | None = None
) -> list[dict]:
    """Mirrors LayoutSectionWiseNewsQuery::handleLivePin() — same filters as
    `layout_section_wise_news`, but live news bubbles to the top regardless of
    stored position (`ORDER BY news.live_news DESC, layout_section_news.position ASC`)."""
    section_stmt = select(LayoutSection.id).where(LayoutSection.slug == section_slug)
    section_id = (await session.execute(section_stmt)).scalar_one_or_none()
    if section_id is None:
        return []
    stmt = (
        select(News, LayoutSectionNews.position)
        .join(LayoutSectionNews, LayoutSectionNews.news_id == News.id)
        .where(
            LayoutSectionNews.layout_section_id == section_id,
            News.deleted_at.is_(None),
            News.published.is_(True),
        )
        .options(selectinload(News.category), selectinload(News.live_news_row))
        .order_by(News.live_news.desc(), LayoutSectionNews.position)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()
    out = []
    for news, position in rows:
        item = await serialize_news_list_item(session, news, include_live_news=True)
        out.append({"position": position, "news": item.model_dump(mode="json")})
    return out


async def category_page_layout_wise_news(
    session: AsyncSession, category_id: int, layout_slug: str, limit: int | None = None
) -> list[dict]:
    """Mirrors CategoryPageLayoutWiseNewsQuery::handle(). Uses an EXISTS-style
    join (news must be published+not-deleted) so, unlike category_layout_wise_news,
    a row whose news fails that filter is excluded entirely (no `{position, news: null}`)."""
    layout_stmt = select(CategoryPageLayout.id).where(
        CategoryPageLayout.category_id == category_id,
        CategoryPageLayout.slug == layout_slug,
        CategoryPageLayout.is_enable.is_(True),
    )
    layout_id = (await session.execute(layout_stmt)).scalar_one_or_none()
    if layout_id is None:
        return []
    stmt = (
        select(News, CategoryPageLayoutNews.position)
        .join(CategoryPageLayoutNews, CategoryPageLayoutNews.news_id == News.id)
        .where(
            CategoryPageLayoutNews.category_page_layout_id == layout_id,
            News.deleted_at.is_(None),
            News.published.is_(True),
        )
        .options(selectinload(News.category))
        .order_by(CategoryPageLayoutNews.position)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = (await session.execute(stmt)).all()
    out = []
    for news, position in rows:
        item = await serialize_news_list_item(session, news)
        out.append({"position": position, "news": item.model_dump(mode="json")})
    return out


async def linked_news(session: AsyncSession, news_id: int) -> list[dict]:
    """Mirrors LinkedNewsQuery::handle($news_id). Only linked articles whose
    target is published are returned."""
    stmt = (
        select(News)
        .join(LinkedNews, LinkedNews.linked_news_id == News.id)
        .where(LinkedNews.main_news_id == news_id, News.published.is_(True), News.deleted_at.is_(None))
        .options(selectinload(News.category))
        .order_by(LinkedNews.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [item.model_dump(mode="json") for item in await serialize_news_list(session, rows)]


async def news_timelines(session: AsyncSession, news_id: int) -> list[dict]:
    """Mirrors NewsTimelinesQuery::handle($news_id). No cache, no pagination —
    every published timeline row for the news item, newest first."""
    stmt = (
        select(NewsTimeline)
        .where(NewsTimeline.news_id == news_id, NewsTimeline.is_publish.is_(True))
        .order_by(NewsTimeline.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "title": t.title,
            "details": t.details,
            "image_path": get_media_url(t.image_path),
            "image_caption": t.image_caption,
            "date": t.date.isoformat() if isinstance(t.date, datetime) else t.date,
        }
        for t in rows
    ]
