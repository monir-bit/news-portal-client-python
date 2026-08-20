"""Port of `App\\Http\\Controllers\\Api\\EpaperQuestionApiController`."""

from fastapi import APIRouter, Body, Depends, Path, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.rate_limit import VOTES, limiter
from app.queries.epaper_queries import (
    get_grid,
    get_page_questions,
    get_participation,
    get_question_detail,
    submit_answer,
)

router = APIRouter(tags=["epaper-question"])


@router.get("/epaper-question/grid")
async def epaper_question_grid(publish_date: str | None = None, db: AsyncSession = Depends(get_db)):
    return await get_grid(db, publish_date)


@router.get("/epaper-question/pages/{page}/questions")
async def epaper_question_page_questions(
    # Mirrors the source route regex `->where('page', '^([1-9]|1[0-6])$')`
    # (1-16, no leading zero). The controller also re-validates the parsed
    # int range as defense-in-depth; `get_page_questions()` keeps that guard.
    page: str = Path(pattern=r"^([1-9]|1[0-6])$"),
    publish_date: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    return await get_page_questions(db, int(page), publish_date)


@router.get("/epaper-question/questions/{question}")
async def epaper_question_show(question: int, db: AsyncSession = Depends(get_db)):
    return await get_question_detail(db, question)


@router.get("/epaper-question/participation")
async def epaper_question_participation(
    question_id: int, phone: str, db: AsyncSession = Depends(get_db)
):
    return await get_participation(db, question_id, phone)


@router.post("/epaper-question/answer")
@limiter.limit(VOTES)
async def epaper_question_answer(
    request: Request,
    response: Response,
    question_id: int = Body(...),
    question_option_id: int = Body(...),
    phone: str = Body(...),
    name: str | None = Body(None),
    email: str | None = Body(None),
    db: AsyncSession = Depends(get_db),
):
    return await submit_answer(
        db,
        question_id=question_id,
        question_option_id=question_option_id,
        phone=phone,
        name=name,
        email=email,
    )
