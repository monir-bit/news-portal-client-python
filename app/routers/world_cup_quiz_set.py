from datetime import date, datetime

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.phone import normalize_phone
from app.core.rate_limit import VOTES, limiter
from app.queries.worldcup_queries import (
    quiz_set_index,
    quiz_set_progress,
    quiz_set_show,
    quiz_set_start,
    quiz_set_submit_answer,
)

router = APIRouter(tags=["world-cup"])


class QuizStartBody(BaseModel):
    name: str = Field(..., max_length=50)
    phone: str = Field(..., max_length=20)
    date_of_birth: date | None = None

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v):
        # Mirrors WorldCupQuizStartRequest::prepareForValidation()'s
        # QuizParticipantPhone::normalize() call (reconstructed — see app/core/phone.py).
        return normalize_phone(v)

    @field_validator("date_of_birth")
    @classmethod
    def _before_today(cls, v):
        if v is not None and v >= datetime.utcnow().date():
            raise ValueError("date_of_birth must be before today")
        return v


class QuizAnswerBody(BaseModel):
    phone: str = Field(..., max_length=20)
    quiz_id: int
    question_option_id: int | None = None
    timed_out: bool = False

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v):
        return normalize_phone(v)


@router.get("/world-cup-quiz-sets")
async def quiz_sets_index_route(db: AsyncSession = Depends(get_db)):
    return await quiz_set_index(db)


@router.get("/world-cup-quiz-sets/{slug}")
async def quiz_set_show_route(slug: str, db: AsyncSession = Depends(get_db)):
    return await quiz_set_show(db, slug)


@router.get("/world-cup-quiz-sets/{slug}/progress")
async def quiz_set_progress_route(slug: str, phone: str = "", db: AsyncSession = Depends(get_db)):
    status_code, content = await quiz_set_progress(db, slug, phone)
    return JSONResponse(status_code=status_code, content=content)


@router.post("/world-cup-quiz-sets/{slug}/start")
async def quiz_set_start_route(
    slug: str, body: QuizStartBody, request: Request, db: AsyncSession = Depends(get_db)
):
    status_code, content = await quiz_set_start(
        db,
        slug,
        body.name,
        body.phone,
        body.date_of_birth,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    return JSONResponse(status_code=status_code, content=content)


@router.post("/world-cup-quiz-sets/{slug}/answer")
@limiter.limit(VOTES)
async def quiz_set_answer_route(
    slug: str, body: QuizAnswerBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    status_code, content = await quiz_set_submit_answer(
        db, slug, body.phone, body.quiz_id, body.question_option_id, body.timed_out
    )
    return JSONResponse(status_code=status_code, content=content)
