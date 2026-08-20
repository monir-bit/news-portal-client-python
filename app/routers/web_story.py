from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.queries.web_story_queries import (
    get_web_story_by_hash,
    serialize_web_story_details,
    slider_data,
    sports_web_story_slider_data,
)

router = APIRouter(tags=["web-story"])


def _not_found(model_name: str) -> HTTPException:
    """Mirrors Laravel's default ModelNotFoundException JSON body; kept
    consistent with this port's established convention (see app/routers/news.py)."""
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{model_name}].")


@router.get("/web-story-slider-data")
async def web_story_slider_data(db: AsyncSession = Depends(get_db)):
    """Mirrors WebStoryController::sliderData(). Deferred: the source caches
    this response for 10 minutes (CacheKey::webStorySliderDataHome()) — no
    caching/Redis in this pass per project scope cut; served uncached."""
    return await slider_data(db)


@router.get("/sports-web-story-slider-data")
async def sports_web_story_slider_data_route(db: AsyncSession = Depends(get_db)):
    """Mirrors WebStoryController::sportsWebHistory(). Deferred: the source
    caches this response for 10 minutes (CacheKey::webStorySliderDataSports())
    — no caching/Redis in this pass per project scope cut; served uncached."""
    return await sports_web_story_slider_data(db)


@router.get("/web-story-details/{hash_key}")
async def web_story_details(hash_key: str, db: AsyncSession = Depends(get_db)):
    """Mirrors WebStoryController::sliderDetails(). Never cached in the source
    either. No `published` filter on the linked news at this level."""
    story = await get_web_story_by_hash(db, hash_key)
    if story is None:
        raise _not_found("WebStory")
    return await serialize_web_story_details(db, story)
