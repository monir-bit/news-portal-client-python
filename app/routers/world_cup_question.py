from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.phone import normalize_phone
from app.core.rate_limit import VOTES, limiter
from app.queries.worldcup_queries import question_submit, questions_index, questions_progress

router = APIRouter(tags=["world-cup"])


class QuestionSubmitBody(BaseModel):
    name: str | None = Field(default=None, max_length=50)
    phone: str = Field(..., min_length=10, max_length=20)
    question_option_id: int

    @field_validator("phone", mode="before")
    @classmethod
    def _normalize_phone(cls, v):
        # Mirrors WorldCupQuestionSubmitRequest::prepareForValidation()'s
        # QuizParticipantPhone::normalize() call (reconstructed — see app/core/phone.py).
        return normalize_phone(v)


@router.get("/world-cup-questions")
async def questions_index_route(phone: str = "", db: AsyncSession = Depends(get_db)):
    return await questions_index(db, phone)


@router.get("/world-cup-questions/progress")
async def questions_progress_route(phone: str = "", db: AsyncSession = Depends(get_db)):
    status_code, content = await questions_progress(db, phone)
    return JSONResponse(status_code=status_code, content=content)


@router.post("/world-cup-questions/{id}/submit")
@limiter.limit(VOTES)
async def question_submit_route(
    id: int, body: QuestionSubmitBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)
):
    status_code, content = await question_submit(
        db,
        id,
        body.name,
        body.phone,
        body.question_option_id,
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
    return JSONResponse(status_code=status_code, content=content)
