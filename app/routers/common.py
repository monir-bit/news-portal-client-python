from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.queries.applications import breaking_news, marque_news, recursive_category_tree, thank_news

router = APIRouter(tags=["common"])


@router.get("/common")
async def common(db: AsyncSession = Depends(get_db)):
    """Mirrors CommonController::common(). Caching is dead/commented-out in the
    source — ported as fully uncached, matching current behavior."""
    return {
        "thank_news": await thank_news(db),
        "site_info": {
            "name": "আগামীর সময়",
            "description": "আগামীর সময় একটি অনলাইন নিউজ পোর্টাল...",
        },
        "categories": await recursive_category_tree(db),
        "marque_news": await marque_news(db),
        "breaking_news": await breaking_news(db),
        "env": settings.app_env,
    }
