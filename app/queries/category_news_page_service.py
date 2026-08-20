"""Python port of app/Services/Api/CategoryNewsPageService.php — shared by the
/news-by-category/{slug} and /news-by-print-category/{slug} routes."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.category_tree import descendant_ids_by_slug
from app.core.pagination import keyset_paginate
from app.models.category import Category
from app.models.geo import District, Division, Upazila
from app.models.layout import PageCategoryMap
from app.models.news import News, NewsLocation
from app.queries.applications import most_read_news_by_category
from app.queries.news_common import category_list_item, serialize_news_list


async def resolve_visible_category(session: AsyncSession, slug: str) -> Category:
    """Mirrors resolveVisibleCategory(): raises NoResultFound (-> 404) if the
    slug doesn't match a visible category."""
    stmt = select(Category).where(Category.slug == slug, Category.visible.is_(True))
    return (await session.execute(stmt)).scalars().one()


async def category_ids_for_slug(session: AsyncSession, slug: str) -> list[int]:
    return await descendant_ids_by_slug(session, slug)


def base_news_query(category_ids: list[int]) -> Select:
    return (
        select(News)
        .where(News.category_id.in_(category_ids), News.published.is_(True), News.deleted_at.is_(None))
        .options(selectinload(News.category))
    )


def apply_date_filter(stmt: Select, date_str: str | None) -> Select:
    """Mirrors applyDateFilter(): no-op if `date_str` is falsy."""
    if not date_str:
        return stmt
    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
    return stmt.where(func.date(News.date) == parsed)


async def apply_geo_filter(
    session: AsyncSession,
    stmt: Select,
    division_slug: str | None,
    district_slug: str | None,
    upazila_slug: str | None,
) -> Select:
    """Mirrors applyGeoFilter(). Cascading-dependency quirk preserved exactly:
    `district_slug` is only honored if `division_slug` was ALSO supplied and
    resolved to a real id; `upazila_slug` only if `district_slug` resolved."""
    if not (division_slug or district_slug or upazila_slug):
        return stmt

    division_id = None
    district_id = None
    upazila_id = None

    if division_slug:
        division_id = (
            await session.execute(select(Division.id).where(Division.slug == division_slug))
        ).scalar_one_or_none()
    if district_slug and division_id is not None:
        district_id = (
            await session.execute(
                select(District.id).where(District.slug == district_slug, District.division_id == division_id)
            )
        ).scalar_one_or_none()
    if upazila_slug and district_id is not None:
        upazila_id = (
            await session.execute(
                select(Upazila.id).where(Upazila.slug == upazila_slug, Upazila.district_id == district_id)
            )
        ).scalar_one_or_none()

    conditions = []
    if division_id is not None:
        conditions.append(NewsLocation.division_id == division_id)
    if district_id is not None:
        conditions.append(NewsLocation.district_id == district_id)
    if upazila_id is not None:
        conditions.append(NewsLocation.upazila_id == upazila_id)
    if not conditions:
        return stmt

    location_news_ids = select(NewsLocation.news_id).where(*conditions)
    return stmt.where(News.id.in_(location_news_ids))


async def paginate_after_leads(
    session: AsyncSession, stmt: Select, cursor: str | None
) -> tuple[list[News], list[News], str | None]:
    """Mirrors paginateAfterLeads(): first 3 matching rows (by the query's own
    ordering) are "lead" news; the next 12 (cursor-paginated) exclude those 3
    lead ids so they never appear twice across lead+listing.

    NOTE: on an infinite-scroll page (`cursor` present) the lead news is not
    used by the router at all, but computing it is cheap relative to the main
    query so it's always computed here for simplicity — same net behavior as
    the source, which also always computes it (see spec notes on wasted work)."""
    ordered = stmt.order_by(News.date.desc(), News.id.desc())
    lead_stmt = ordered.limit(3)
    lead_news = list((await session.execute(lead_stmt)).scalars().all())
    lead_ids = [n.id for n in lead_news]

    rest_stmt = stmt
    if lead_ids:
        rest_stmt = rest_stmt.where(News.id.notin_(lead_ids))
    page, next_cursor = await keyset_paginate(session, rest_stmt, News.date, News.id, 12, cursor)
    return lead_news, page, next_cursor


async def categories_ordered_for_print_edition(session: AsyncSession, date_str: str) -> list[Category]:
    """Mirrors categoriesOrderedForPrintEdition($date)."""
    parsed = datetime.strptime(date_str, "%Y-%m-%d").date()
    stmt = (
        select(PageCategoryMap)
        .join(Category, Category.id == PageCategoryMap.category_id)
        .where(PageCategoryMap.date == parsed, Category.visible.is_(True))
        .options(selectinload(PageCategoryMap.category))
        .order_by(PageCategoryMap.position)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [m.category for m in rows]


async def build_full_listing_payload(
    session: AsyncSession,
    category: Category,
    lead_news: list[News],
    news_page: list[News],
    next_cursor: str | None,
    print_edition_children: list[Category] | None = None,
) -> dict:
    """Mirrors buildFullListingPayload()."""
    from app.core.seo import make_seo

    category_seo_stmt = select(Category).where(Category.id == category.id).options(selectinload(Category.category_seo))
    category_with_seo = (await session.execute(category_seo_stmt)).scalar_one()
    seo = category_with_seo.category_seo

    if print_edition_children is not None:
        children_categories = print_edition_children
    else:
        children_stmt = select(Category).where(Category.parent_id == category.id).order_by(Category.position)
        children_categories = list((await session.execute(children_stmt)).scalars().all())
        if not children_categories and category.parent_id is not None:
            siblings_stmt = (
                select(Category).where(Category.parent_id == category.parent_id).order_by(Category.position)
            )
            children_categories = list((await session.execute(siblings_stmt)).scalars().all())

    if category.parent_id is not None:
        parent = (await session.execute(select(Category).where(Category.id == category.parent_id))).scalar_one()
    else:
        parent = category

    most_read = await most_read_news_by_category(session, category.id)

    return {
        "category": (await category_list_item(session, category)).model_dump(mode="json"),
        "seo_meta": make_seo(
            title=(seo.title if seo and seo.title else category.name),
            image=(seo.og_image if seo else "") or "",
            description=(seo.description if seo else "") or "",
            keywords=(seo.keywords if seo and seo.keywords else []),
        ),
        "parent": (await category_list_item(session, parent)).model_dump(mode="json"),
        "children": [(await category_list_item(session, c)).model_dump(mode="json") for c in children_categories],
        "news_list": {
            "lead_news": [i.model_dump(mode="json") for i in await serialize_news_list(session, lead_news)],
            "news": {
                "data": [i.model_dump(mode="json") for i in await serialize_news_list(session, news_page)],
                "links": {"next": (f"?cursor={next_cursor}" if next_cursor else None), "prev": None},
                "meta": {"next_cursor": next_cursor, "prev_cursor": None},
            },
        },
        "most_read_news": most_read,
    }
