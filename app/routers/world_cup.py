from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.queries.worldcup_queries import all_matches, match_details, today_match

router = APIRouter(tags=["world-cup"])


@router.get("/world-cup-today-match")
async def today_match_route(db: AsyncSession = Depends(get_db)):
    return await today_match(db)


@router.get("/world-cup-match-details/{id}")
async def match_details_route(id: int, db: AsyncSession = Depends(get_db)):
    return await match_details(db, id)


@router.get("/world-cup-all-matches")
async def all_matches_route(db: AsyncSession = Depends(get_db)):
    return {"match_data": await all_matches(db)}
