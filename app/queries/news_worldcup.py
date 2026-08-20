from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import portal_time
from app.models.category import Category
from app.models.worldcup import WorldCupMatch, WorldCupMatchCommentary, WorldCupQuizSet
from app.queries.applications import category_page_layout_wise_news


async def news_by_category_world_cup(session: AsyncSession) -> dict:
    """Mirrors NewsController::newsByCategoryWorldCup(). Raises NoResultFound
    (-> 404) if the 'world-cup' category is missing/invisible."""
    category = (
        await session.execute(
            select(Category)
            .where(Category.slug == "world-cup", Category.visible.is_(True))
            .options(selectinload(Category.children), selectinload(Category.parent))
        )
    ).scalars().one()

    now = portal_time.now()
    window_from = now - timedelta(hours=24)
    window_to = (now + timedelta(days=10)).replace(hour=23, minute=59, second=59, microsecond=999999)
    stmt = (
        select(WorldCupMatch)
        .where(
            WorldCupMatch.season == "2026",
            WorldCupMatch.status.in_(["scheduled", "live"]),
            text("(match_date + start_time) BETWEEN :window_from AND :window_to"),
        )
        .params(window_from=window_from, window_to=window_to)
        .options(
            selectinload(WorldCupMatch.home_team),
            selectinload(WorldCupMatch.away_team),
            selectinload(WorldCupMatch.commentaries),
        )
        .order_by(WorldCupMatch.match_date, WorldCupMatch.start_time)
        .limit(5)
    )
    matches = (await session.execute(stmt)).scalars().all()

    quiz_set_slug = (
        await session.execute(
            select(WorldCupQuizSet.slug).where(
                WorldCupQuizSet.is_active.is_(True),
                WorldCupQuizSet.start_time <= now,
                WorldCupQuizSet.end_time >= now,
            )
        )
    ).scalar_one_or_none()

    def match_dict(m: WorldCupMatch) -> dict:
        commentaries = sorted(m.commentaries, key=lambda c: c.created_at or datetime.min, reverse=True)[:2]
        return {
            "id": m.id,
            "team_a_score": m.team_a_score,
            "team_b_score": m.team_b_score,
            "team_a_penalty_score": m.team_a_penalty_score,
            "team_b_penalty_score": m.team_b_penalty_score,
            "match_date": m.match_date.isoformat() if m.match_date else None,
            "start_time": m.start_time.isoformat() if m.start_time else None,
            "venue": m.venue,
            "title": m.title,
            "stage": m.stage,
            "group_name": m.group_name,
            "status": m.status,
            "news_id": m.news_id,
            "home_team": {
                "id": m.home_team.id, "name": m.home_team.name,
                "flag_icon": m.home_team.flag_icon, "group": m.home_team.group,
                "fifa_code": m.home_team.fifa_code,
            },
            "away_team": {
                "id": m.away_team.id, "name": m.away_team.name,
                "flag_icon": m.away_team.flag_icon, "group": m.away_team.group,
                "fifa_code": m.away_team.fifa_code,
            },
            "commentaries": [
                {"id": c.id, "match_id": c.match_id, "description": c.description,
                 "created_at": c.created_at.isoformat() if c.created_at else None}
                for c in commentaries
            ],
        }

    return {
        "lead_news": await category_page_layout_wise_news(session, category.id, "lead-news", 10),
        "holud_jhor": await category_page_layout_wise_news(session, category.id, "holud-jhor", 8),
        "akashi_hawa": await category_page_layout_wise_news(session, category.id, "akashi-hawa", 8),
        "world_cup_analysis": await category_page_layout_wise_news(session, category.id, "world-cup-analysis", 1),
        "world_cup_history": await category_page_layout_wise_news(session, category.id, "world-cup-history", 1),
        "star_news": await category_page_layout_wise_news(session, category.id, "star-news", 1),
        "world_cup_thinking": await category_page_layout_wise_news(session, category.id, "world-cup-thinking", 1),
        "matches": [match_dict(m) for m in matches],
        "quiz_set_slug": quiz_set_slug,
    }
