from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import LayoutSectionEnum
from app.queries.applications import (
    latest_news,
    layout_section_wise_news,
    layout_section_wise_news_live_pin,
    most_read_news,
    special_segment_news,
)

router = APIRouter(tags=["home"])


@router.get("/home")
async def home_initial(db: AsyncSession = Depends(get_db)):
    """Mirrors HomeController::homeInitial(). Caching is dead/commented-out in
    the source (see spec) — ported as fully uncached, matching current behavior.

    `editors_pick`'s underlying layout section slug is locale-dependent in the
    source (`en` -> 'editors-pick', else -> 'feature-box'). This port has no
    request-locale concept (the whole API is unauthenticated/localeless), so it
    always uses the Bengali-site default `'feature-box'` — flagged in the
    implementation guide as a follow-up if English-locale support is added."""
    editors_pick_slug = LayoutSectionEnum.FEATURE_BOX.value

    return {
        "trending_video_news": await layout_section_wise_news(db, "trending-video-news", 4),
        "lead_news": await layout_section_wise_news(db, "lead-news", 5),
        "world_cup_lead": await layout_section_wise_news_live_pin(db, "world-cup-lead", 5),
        "pin_news": await layout_section_wise_news(db, "pin-news", 4),
        "sub_lead_news": await layout_section_wise_news(db, "sub-lead-news", 12),
        "editors_pick": await layout_section_wise_news(db, editors_pick_slug, 1),
        "latest_news": await latest_news(db),
        "most_read_news": await most_read_news(db),
        "special_segment_news": await special_segment_news(db),
        "opinion": await layout_section_wise_news(db, "opinion", 1),
        "advice": await layout_section_wise_news(db, "advice", 1),
        "fact_check": await layout_section_wise_news(db, "fact-check", 1),
        "analysis": await layout_section_wise_news(db, "analysis", 1),
    }
