from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.category_tree import descendant_ids_by_slug
from app.core.pagination import cursor_page_envelope, keyset_paginate
from app.models.category import Category
from app.models.news import News
from app.queries.applications import (
    category_page_layout_wise_news,
    latest_news,
    most_read_news,
    most_read_news_by_category,
)
from app.queries.news_common import category_list_item, serialize_news_list


async def news_by_category_sports(session: AsyncSession, cursor: str | None) -> dict:
    """Mirrors NewsController::newsByCategorySports()."""
    category = (
        await session.execute(
            select(Category)
            .where(Category.slug == "sports", Category.visible.is_(True))
            .options(selectinload(Category.children), selectinload(Category.parent))
        )
    ).scalars().one()  # -> 404 if missing/invisible

    football_category = (
        await session.execute(select(Category).where(Category.slug == "football"))
    ).scalars().first()
    cricket_category = (
        await session.execute(select(Category).where(Category.slug == "cricket"))
    ).scalars().first()

    cricket_news, football_news = [], []
    if cricket_category is not None:
        cricket_ids = await descendant_ids_by_slug(session, cricket_category.slug)
        stmt = (
            select(News)
            .where(News.category_id.in_(cricket_ids), News.deleted_at.is_(None))
            .options(selectinload(News.category))
            .order_by(News.date.desc())
            .limit(9)
        )
        cricket_news = list((await session.execute(stmt)).scalars().all())
    if football_category is not None:
        football_ids = await descendant_ids_by_slug(session, football_category.slug)
        stmt = (
            select(News)
            .where(News.category_id.in_(football_ids), News.deleted_at.is_(None))
            .options(selectinload(News.category))
            .order_by(News.date.desc())
            .limit(9)
        )
        football_news = list((await session.execute(stmt)).scalars().all())

    others_stmt = select(News).where(News.published.is_(True), News.deleted_at.is_(None))
    if category.parent_id:
        others_stmt = others_stmt.where(News.category_id == category.id)
    else:
        exclude = {c.id for c in [football_category, cricket_category] if c is not None}
        child_ids = [c.id for c in category.children if c.id not in exclude] + [category.id]
        others_stmt = others_stmt.where(News.category_id.in_(child_ids))
    others_stmt = others_stmt.options(selectinload(News.category))

    others_page, next_cursor = await keyset_paginate(session, others_stmt, News.created_at, News.id, 12, cursor)
    others_items = [i.model_dump(mode="json") for i in await serialize_news_list(session, others_page)]

    if cursor:
        return cursor_page_envelope(others_items, next_cursor, 12, "/api/news-by-category-sports")

    parent_category = category.parent if category.parent_id else category
    return {
        "category": (await category_list_item(session, category)).model_dump(mode="json"),
        "parent": (await category_list_item(session, parent_category)).model_dump(mode="json"),
        "children": [(await category_list_item(session, c)).model_dump(mode="json") for c in category.children],
        "news_list": {
            "lead": await category_page_layout_wise_news(session, category.id, "lead", 6),
            "selected": await category_page_layout_wise_news(session, category.id, "selected", 15),
            "cricket": [i.model_dump(mode="json") for i in await serialize_news_list(session, cricket_news)],
            "football": [i.model_dump(mode="json") for i in await serialize_news_list(session, football_news)],
            "others": cursor_page_envelope(others_items, next_cursor, 12, "/api/news-by-category-sports"),
        },
        "latest_news": await latest_news(session),
        "most_read_news_all": await most_read_news(session),
        "most_read_news": await most_read_news_by_category(session, category.id, 5),
    }
