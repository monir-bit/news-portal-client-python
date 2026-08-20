"""Business logic for the World Cup domain (WorldCupController,
WorldCupQuizSetController, WorldCupQuestionController ports).

Conventions used throughout this module:
- GET-only helpers return plain data (list/dict) and raise `HTTPException`
  for "not found" cases (mirroring `app/routers/news.py`'s `not_found()`).
- Endpoints with multiple possible outcomes (success + one or more flat,
  multi-key 4xx bodies) return a `(status_code, content_dict)` tuple; the
  router wraps that directly in a `JSONResponse` so the exact top-level key
  names from the spec (e.g. `already_completed`, `already_answered`) are
  preserved instead of being nested under a `detail` key.
- Every write path commits before returning; races on the two DB-unique-
  constraint-backed duplicate-submission guards are caught as
  `IntegrityError` and translated into the same friendly 422 body the
  app-level `exists()` check would have produced.
"""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.media import get_media_url
from app.models.participant import Participant
from app.models.worldcup import (
    WorldCupMatch,
    WorldCupQuestion,
    WorldCupQuestionOption,
    WorldCupQuestionParticipation,
    WorldCupQuiz,
    WorldCupQuizAnswer,
    WorldCupQuizOption,
    WorldCupQuizParticipation,
    WorldCupQuizSet,
)

SEASON = "2026"


def _not_found(model_name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{model_name}].")


# ---------------------------------------------------------------------------
# WorldCupController
# ---------------------------------------------------------------------------

def _commentary_dicts(commentaries, limit: int | None = None) -> list[dict]:
    ordered = sorted(commentaries, key=lambda c: c.created_at or datetime.min, reverse=True)
    if limit is not None:
        ordered = ordered[:limit]
    return [
        {
            "id": c.id,
            "match_id": c.match_id,
            "description": c.description,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in ordered
    ]


def _match_base_dict(m: WorldCupMatch, commentary_limit: int | None) -> dict:
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
            "id": m.home_team.id,
            "name": m.home_team.name,
            "flag_icon": m.home_team.flag_icon,
            "group": m.home_team.group,
            "fifa_code": m.home_team.fifa_code,
        },
        "away_team": {
            "id": m.away_team.id,
            "name": m.away_team.name,
            "flag_icon": m.away_team.flag_icon,
            "group": m.away_team.group,
            "fifa_code": m.away_team.fifa_code,
        },
        "commentaries": _commentary_dicts(m.commentaries, commentary_limit),
    }


def _match_details_dict(m: WorldCupMatch) -> dict:
    d = _match_base_dict(m, None)
    timelines = [t for t in m.time_lines if t.is_publish]
    timelines.sort(key=lambda t: t.date or datetime.min, reverse=True)
    d["time_lines"] = [
        {
            "news_id": t.news_id,
            "title": t.title,
            "details": t.details,
            "date": t.date.isoformat() if t.date else None,
            # Raw column (not run through get_media_url) — the Laravel eager-load
            # closure selects the bare `image_path` column, no resource/accessor.
            "image_path": t.image_path,
            "image_caption": t.image_caption,
        }
        for t in timelines
    ]
    return d


async def today_match(db: AsyncSession) -> list[dict]:
    now = datetime.utcnow()
    window_from = now - timedelta(hours=24)
    window_to = (now + timedelta(days=10)).replace(hour=23, minute=59, second=59, microsecond=999999)
    stmt = (
        select(WorldCupMatch)
        .where(
            WorldCupMatch.season == SEASON,
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
        .limit(6)
    )
    matches = (await db.execute(stmt)).scalars().all()
    return [_match_base_dict(m, 2) for m in matches]


async def all_matches(db: AsyncSession) -> list[dict]:
    stmt = (
        select(WorldCupMatch)
        .where(WorldCupMatch.season == SEASON)
        .options(
            selectinload(WorldCupMatch.home_team),
            selectinload(WorldCupMatch.away_team),
            selectinload(WorldCupMatch.commentaries),
        )
        .order_by(WorldCupMatch.match_date, WorldCupMatch.start_time)
    )
    matches = (await db.execute(stmt)).scalars().all()
    return [_match_base_dict(m, 2) for m in matches]


async def match_details(db: AsyncSession, match_id: int) -> dict:
    stmt = (
        select(WorldCupMatch)
        .where(WorldCupMatch.season == SEASON, WorldCupMatch.id == match_id)
        .options(
            selectinload(WorldCupMatch.home_team),
            selectinload(WorldCupMatch.away_team),
            selectinload(WorldCupMatch.commentaries),
            selectinload(WorldCupMatch.time_lines),
        )
        .order_by(WorldCupMatch.match_date, WorldCupMatch.start_time)
    )
    m = (await db.execute(stmt)).scalars().first()
    if m is None:
        # Deviation from source: Laravel calls ->makeHidden() unconditionally on a
        # possibly-null result here, which fatals into a 500. Per product decision,
        # this port returns a clean 404 instead.
        raise _not_found("WorldCupMatch")
    return {"match_data": _match_details_dict(m)}


# ---------------------------------------------------------------------------
# WorldCupQuizSetController
# ---------------------------------------------------------------------------

def _quiz_set_active_now_clauses(now: datetime):
    return (
        WorldCupQuizSet.is_active.is_(True),
        or_(WorldCupQuizSet.start_time.is_(None), WorldCupQuizSet.start_time <= now),
        or_(WorldCupQuizSet.end_time.is_(None), WorldCupQuizSet.end_time >= now),
    )


async def _active_quizzes(db: AsyncSession, set_id: int, with_options: bool = False) -> list[WorldCupQuiz]:
    stmt = (
        select(WorldCupQuiz)
        .where(WorldCupQuiz.world_cup_quiz_set_id == set_id, WorldCupQuiz.is_active.is_(True))
        .order_by(WorldCupQuiz.sort_order, WorldCupQuiz.id)
    )
    if with_options:
        stmt = stmt.options(selectinload(WorldCupQuiz.options))
    return list((await db.execute(stmt)).scalars().all())


async def quiz_set_index(db: AsyncSession) -> list[dict]:
    now = datetime.utcnow()
    active_count_subq = (
        select(
            WorldCupQuiz.world_cup_quiz_set_id.label("set_id"),
            func.count(WorldCupQuiz.id).label("cnt"),
        )
        .where(WorldCupQuiz.is_active.is_(True))
        .group_by(WorldCupQuiz.world_cup_quiz_set_id)
        .subquery()
    )
    stmt = (
        select(WorldCupQuizSet, active_count_subq.c.cnt)
        .join(active_count_subq, active_count_subq.c.set_id == WorldCupQuizSet.id)
        .where(*_quiz_set_active_now_clauses(now))
        .order_by(WorldCupQuizSet.id.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "slug": s.slug,
            "image_url": get_media_url(s.image),
            "is_active": s.is_active,
            "start_time": s.start_time.isoformat() if s.start_time else None,
            "end_time": s.end_time.isoformat() if s.end_time else None,
            "quizzes_count": int(cnt),
        }
        for s, cnt in rows
    ]


async def quiz_set_show(db: AsyncSession, slug: str) -> dict:
    now = datetime.utcnow()
    quiz_set = (
        await db.execute(select(WorldCupQuizSet).where(WorldCupQuizSet.slug == slug, *_quiz_set_active_now_clauses(now)))
    ).scalars().first()
    if quiz_set is None:
        raise _not_found("WorldCupQuizSet")

    quizzes = await _active_quizzes(db, quiz_set.id, with_options=True)
    if not quizzes:
        raise HTTPException(status_code=404, detail="Not Found.")

    return {
        "id": quiz_set.id,
        "name": quiz_set.name,
        "slug": quiz_set.slug,
        "image_url": get_media_url(quiz_set.image),
        "is_active": quiz_set.is_active,
        "start_time": quiz_set.start_time.isoformat() if quiz_set.start_time else None,
        "end_time": quiz_set.end_time.isoformat() if quiz_set.end_time else None,
        "quizzes": [
            {
                "id": q.id,
                "question": q.question,
                "description": q.description,
                "image_url": get_media_url(q.image),
                "duration_seconds": q.duration_seconds,
                "sort_order": q.sort_order,
                "options": [{"id": o.id, "option_text": o.option_text} for o in q.options],
            }
            for q in quizzes
        ],
    }


async def quiz_set_progress(db: AsyncSession, slug: str, phone: str) -> tuple[int, dict]:
    now = datetime.utcnow()
    quiz_set = (
        await db.execute(select(WorldCupQuizSet).where(WorldCupQuizSet.slug == slug, *_quiz_set_active_now_clauses(now)))
    ).scalars().first()
    if quiz_set is None:
        raise _not_found("WorldCupQuizSet")

    phone = phone or ""
    if phone == "":
        return 422, {"message": "Phone is required."}

    no_participation = {"has_participation": False, "completed": False, "answered_quiz_ids": []}

    participant = (await db.execute(select(Participant).where(Participant.phone == phone))).scalars().first()
    if participant is None:
        return 200, no_participation

    participation = (
        await db.execute(
            select(WorldCupQuizParticipation).where(
                WorldCupQuizParticipation.world_cup_quiz_set_id == quiz_set.id,
                WorldCupQuizParticipation.participant_id == participant.id,
            )
        )
    ).scalars().first()
    if participation is None:
        return 200, no_participation

    answered_ids = list(
        (
            await db.execute(
                select(WorldCupQuizAnswer.world_cup_quiz_id)
                .where(WorldCupQuizAnswer.world_cup_quiz_participation_id == participation.id)
                .order_by(WorldCupQuizAnswer.id)
            )
        ).scalars().all()
    )

    return 200, {
        "has_participation": True,
        "completed": participation.completed_at is not None,
        "score": participation.score,
        "total_questions": participation.total_questions,
        "answered_quiz_ids": answered_ids,
    }


async def quiz_set_start(
    db: AsyncSession,
    slug: str,
    name: str,
    phone: str,
    date_of_birth,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[int, dict]:
    now = datetime.utcnow()
    quiz_set = (
        await db.execute(select(WorldCupQuizSet).where(WorldCupQuizSet.slug == slug, *_quiz_set_active_now_clauses(now)))
    ).scalars().first()
    if quiz_set is None:
        raise _not_found("WorldCupQuizSet")

    active_quizzes = await _active_quizzes(db, quiz_set.id)
    if not active_quizzes:
        raise HTTPException(status_code=404, detail="Not Found.")

    name = name.strip()
    participant = (await db.execute(select(Participant).where(Participant.phone == phone))).scalars().first()
    if participant is not None:
        participant.name = name
        if date_of_birth is not None:
            participant.date_of_birth = date_of_birth
    else:
        participant = Participant(name=name, phone=phone, date_of_birth=date_of_birth)
        db.add(participant)
    await db.flush()

    existing = (
        await db.execute(
            select(WorldCupQuizParticipation).where(
                WorldCupQuizParticipation.world_cup_quiz_set_id == quiz_set.id,
                WorldCupQuizParticipation.participant_id == participant.id,
            )
        )
    ).scalars().first()

    if existing is not None and existing.completed_at is not None:
        await db.commit()
        return 422, {
            "message": "You have already completed this quiz set.",
            "already_completed": True,
            "score": existing.score,
            "total_questions": existing.total_questions,
        }

    if existing is not None:
        participation = existing
    else:
        participation = WorldCupQuizParticipation(
            world_cup_quiz_set_id=quiz_set.id,
            participant_id=participant.id,
            total_questions=len(active_quizzes),
            started_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.add(participation)
        await db.flush()

    await db.commit()

    answered_ids = list(
        (
            await db.execute(
                select(WorldCupQuizAnswer.world_cup_quiz_id)
                .where(WorldCupQuizAnswer.world_cup_quiz_participation_id == participation.id)
                .order_by(WorldCupQuizAnswer.id)
            )
        ).scalars().all()
    )

    return 201, {
        "message": "Quiz started.",
        "participation_id": participation.id,
        "total_questions": participation.total_questions,
        "answered_quiz_ids": answered_ids,
        "completed": False,
        "score": participation.score,
    }


async def quiz_set_submit_answer(
    db: AsyncSession,
    slug: str,
    phone: str,
    quiz_id: int,
    question_option_id: int | None,
    timed_out: bool,
) -> tuple[int, dict]:
    now = datetime.utcnow()
    quiz_set = (
        await db.execute(select(WorldCupQuizSet).where(WorldCupQuizSet.slug == slug, *_quiz_set_active_now_clauses(now)))
    ).scalars().first()
    if quiz_set is None:
        raise _not_found("WorldCupQuizSet")

    active_quizzes = await _active_quizzes(db, quiz_set.id)

    participant = (await db.execute(select(Participant).where(Participant.phone == phone))).scalars().first()
    if participant is None:
        raise _not_found("Participant")

    participation = (
        await db.execute(
            select(WorldCupQuizParticipation).where(
                WorldCupQuizParticipation.world_cup_quiz_set_id == quiz_set.id,
                WorldCupQuizParticipation.participant_id == participant.id,
            )
        )
    ).scalars().first()
    if participation is None:
        raise _not_found("WorldCupQuizParticipation")

    if participation.completed_at is not None:
        return 422, {
            "message": "Quiz already completed.",
            "already_completed": True,
            "score": participation.score,
            "total_questions": participation.total_questions,
        }

    quiz = (
        await db.execute(
            select(WorldCupQuiz).where(
                WorldCupQuiz.world_cup_quiz_set_id == quiz_set.id,
                WorldCupQuiz.is_active.is_(True),
                WorldCupQuiz.id == quiz_id,
            )
        )
    ).scalars().first()
    if quiz is None:
        raise _not_found("WorldCupQuiz")

    already_answered = (
        await db.execute(
            select(WorldCupQuizAnswer.id).where(
                WorldCupQuizAnswer.world_cup_quiz_participation_id == participation.id,
                WorldCupQuizAnswer.world_cup_quiz_id == quiz.id,
            )
        )
    ).scalars().first()
    if already_answered is not None:
        return 422, {"message": "This question was already answered.", "already_answered": True}

    option = None
    is_correct = False
    if not timed_out and question_option_id:
        option = (
            await db.execute(
                select(WorldCupQuizOption).where(
                    WorldCupQuizOption.world_cup_quiz_id == quiz.id,
                    WorldCupQuizOption.id == question_option_id,
                )
            )
        ).scalars().first()
        if option is None:
            raise _not_found("WorldCupQuizOption")
        is_correct = bool(option.is_correct)

    answer = WorldCupQuizAnswer(
        world_cup_quiz_participation_id=participation.id,
        world_cup_quiz_id=quiz.id,
        world_cup_quiz_option_id=option.id if option else None,
        is_correct=is_correct,
        timed_out=timed_out,
        answered_at=now,
    )
    db.add(answer)
    try:
        await db.flush()
    except IntegrityError:
        # Race backstop: `wc_quiz_answers_participation_quiz_unique` fired between
        # the exists() check above and this insert — translate to the same 422
        # the app-level check would have produced.
        await db.rollback()
        return 422, {"message": "This question was already answered.", "already_answered": True}

    if is_correct:
        await db.execute(
            update(WorldCupQuizParticipation)
            .where(WorldCupQuizParticipation.id == participation.id)
            .values(score=WorldCupQuizParticipation.score + 1)
        )

    answered_count = (
        await db.execute(
            select(func.count())
            .select_from(WorldCupQuizAnswer)
            .where(WorldCupQuizAnswer.world_cup_quiz_participation_id == participation.id)
        )
    ).scalar_one()

    total_questions = participation.total_questions
    completed = answered_count >= total_questions
    if completed and participation.completed_at is None:
        participation.completed_at = now

    await db.commit()
    await db.refresh(participation)

    answered_ids = list(
        (
            await db.execute(
                select(WorldCupQuizAnswer.world_cup_quiz_id)
                .where(WorldCupQuizAnswer.world_cup_quiz_participation_id == participation.id)
                .order_by(WorldCupQuizAnswer.id)
            )
        ).scalars().all()
    )

    next_quiz = next((q for q in active_quizzes if q.id not in answered_ids), None)

    return 201, {
        "message": "Answer recorded.",
        "is_correct": is_correct,
        "timed_out": timed_out,
        "score": participation.score,
        "completed": completed,
        "answered_quiz_ids": answered_ids,
        "next_quiz_id": next_quiz.id if next_quiz else None,
    }


# ---------------------------------------------------------------------------
# WorldCupQuestionController
# ---------------------------------------------------------------------------

def _question_submission_status(q: WorldCupQuestion, now: datetime) -> str:
    if not q.is_active:
        return "inactive"
    if q.start_date_time is not None and now < q.start_date_time:
        return "upcoming"
    if q.end_date_time is not None and now > q.end_date_time:
        return "ended"
    return "open"


def _question_is_submittable(q: WorldCupQuestion, now: datetime, options_count: int) -> bool:
    if not q.is_active:
        return False
    if q.start_date_time is not None and now < q.start_date_time:
        return False
    if q.end_date_time is not None and now > q.end_date_time:
        return False
    return options_count >= 2


async def questions_index(db: AsyncSession, phone: str) -> list[dict]:
    phone = phone or ""
    answered_ids: list[int] = []
    if phone != "":
        participant = (await db.execute(select(Participant).where(Participant.phone == phone))).scalars().first()
        if participant is not None:
            answered_ids = list(
                (
                    await db.execute(
                        select(WorldCupQuestionParticipation.world_cup_question_id).where(
                            WorldCupQuestionParticipation.participant_id == participant.id
                        )
                    )
                ).scalars().all()
            )

    now = datetime.utcnow()
    stmt = (
        select(WorldCupQuestion)
        .options(selectinload(WorldCupQuestion.options))
        .order_by(WorldCupQuestion.sort_order, WorldCupQuestion.id)
    )
    questions = (await db.execute(stmt)).scalars().all()

    result = []
    for q in questions:
        options_count = len(q.options)
        result.append(
            {
                "id": q.id,
                "question": q.question,
                "description": q.description,
                "image_url": get_media_url(q.image),
                "duration_seconds": q.duration_seconds,
                "sort_order": q.sort_order,
                "is_active": q.is_active,
                "start_date_time": q.start_date_time.isoformat() if q.start_date_time else None,
                "end_date_time": q.end_date_time.isoformat() if q.end_date_time else None,
                "submission_status": _question_submission_status(q, now),
                "is_submittable": _question_is_submittable(q, now, options_count),
                "has_answered": q.id in answered_ids,
                "options": [{"id": o.id, "option_text": o.option_text} for o in q.options],
            }
        )
    return result


async def questions_progress(db: AsyncSession, phone: str) -> tuple[int, dict]:
    phone = phone or ""
    if phone == "":
        return 422, {"message": "Phone is required."}

    participant = (await db.execute(select(Participant).where(Participant.phone == phone))).scalars().first()
    if participant is None:
        return 200, {"answered_question_ids": []}

    ids = list(
        (
            await db.execute(
                select(WorldCupQuestionParticipation.world_cup_question_id).where(
                    WorldCupQuestionParticipation.participant_id == participant.id
                )
            )
        ).scalars().all()
    )
    return 200, {"answered_question_ids": ids}


async def question_submit(
    db: AsyncSession,
    question_id: int,
    name: str | None,
    phone: str,
    question_option_id: int,
    ip_address: str | None,
    user_agent: str | None,
) -> tuple[int, dict]:
    # Mirrors WorldCupQuestionSubmitRequest's `exists:world_cup_question_options,id`
    # rule — Laravel's Form Request validation runs before any controller logic,
    # so an option id that doesn't exist ANYWHERE fails validation before the
    # question itself is ever looked up (this check is scope-blind by design;
    # the per-question scoping check happens later).
    option_exists = (
        await db.execute(select(WorldCupQuestionOption.id).where(WorldCupQuestionOption.id == question_option_id))
    ).scalars().first()
    if option_exists is None:
        return 422, {
            "message": "The selected question option id is invalid.",
            "errors": {"question_option_id": ["The selected question option id is invalid."]},
        }

    participant = (await db.execute(select(Participant).where(Participant.phone == phone))).scalars().first()

    # Mirrors WorldCupQuestionSubmitRequest's dynamic `name` rule: required
    # unless the phone already belongs to a known participant.
    if participant is None and not (name and name.strip()):
        return 422, {
            "message": "The name field is required.",
            "errors": {"name": ["The name field is required."]},
        }

    question = (
        await db.execute(
            select(WorldCupQuestion).options(selectinload(WorldCupQuestion.options)).where(WorldCupQuestion.id == question_id)
        )
    ).scalars().first()
    if question is None:
        raise _not_found("WorldCupQuestion")

    now = datetime.utcnow()
    if not _question_is_submittable(question, now, len(question.options)):
        return 422, {"message": "This question is not open for submission.", "not_submittable": True}

    option = next((o for o in question.options if o.id == question_option_id), None)
    if option is None:
        raise _not_found("WorldCupQuestionOption")

    if participant is not None:
        if name and name.strip():
            participant.name = name.strip()
    else:
        participant = Participant(name=name.strip(), phone=phone)
        db.add(participant)
        await db.flush()

    existing = (
        await db.execute(
            select(WorldCupQuestionParticipation).where(
                WorldCupQuestionParticipation.world_cup_question_id == question.id,
                WorldCupQuestionParticipation.participant_id == participant.id,
            )
        )
    ).scalars().first()
    if existing is not None:
        await db.commit()
        return 422, {
            "message": "You have already answered this question.",
            "already_answered": True,
            "is_correct": existing.is_correct,
        }

    is_correct = bool(option.is_correct)
    participation = WorldCupQuestionParticipation(
        world_cup_question_id=question.id,
        participant_id=participant.id,
        world_cup_question_option_id=option.id,
        is_correct=is_correct,
        submitted_at=now,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(participation)
    try:
        await db.commit()
    except IntegrityError:
        # Race backstop: `wc_question_participations_question_participant_unique`
        # fired between the exists() check above and this insert.
        await db.rollback()
        existing2 = (
            await db.execute(
                select(WorldCupQuestionParticipation).where(
                    WorldCupQuestionParticipation.world_cup_question_id == question.id,
                    WorldCupQuestionParticipation.participant_id == participant.id,
                )
            )
        ).scalars().first()
        return 422, {
            "message": "You have already answered this question.",
            "already_answered": True,
            "is_correct": existing2.is_correct if existing2 else is_correct,
        }

    return 201, {"message": "Answer recorded.", "is_correct": is_correct, "question_id": question.id}
