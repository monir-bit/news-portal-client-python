from datetime import date, datetime, time

from sqlalchemy import ForeignKey, SmallInteger
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.news import NewsTimeline


class WorldCupTeam(Base):
    __tablename__ = "world_cup_teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    name_normalised: Mapped[str | None]
    continent: Mapped[str]
    flag_icon: Mapped[str]
    flag_unicode: Mapped[str | None]
    fifa_code: Mapped[str] = mapped_column(unique=True)
    group: Mapped[str]
    confed: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class WorldCupMatch(Base):
    __tablename__ = "world_cup_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_a: Mapped[int] = mapped_column(ForeignKey("world_cup_teams.id"))
    team_b: Mapped[int] = mapped_column(ForeignKey("world_cup_teams.id"))
    team_a_score: Mapped[int] = mapped_column(default=0)
    team_b_score: Mapped[int] = mapped_column(default=0)
    team_a_penalty_score: Mapped[int | None]
    team_b_penalty_score: Mapped[int | None]
    match_date: Mapped[date]
    start_time: Mapped[time]
    venue: Mapped[str | None]
    title: Mapped[str | None]
    season: Mapped[str] = mapped_column(default="2026")
    stage: Mapped[str | None]
    group_name: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="scheduled")
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    home_team: Mapped["WorldCupTeam"] = relationship(foreign_keys=[team_a])
    away_team: Mapped["WorldCupTeam"] = relationship(foreign_keys=[team_b])
    commentaries: Mapped[list["WorldCupMatchCommentary"]] = relationship(back_populates="match")
    # Joins on news_id = news_id (NOT the match's own PK) — mirrors
    # `hasMany(NewsTimeline::class, 'news_id', 'news_id')` in the Laravel model.
    time_lines: Mapped[list["NewsTimeline"]] = relationship(
        primaryjoin="foreign(NewsTimeline.news_id) == WorldCupMatch.news_id",
        viewonly=True,
    )


class WorldCupMatchCommentary(Base):
    __tablename__ = "world_cup_match_commentaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("world_cup_matches.id"))
    description: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    match: Mapped["WorldCupMatch"] = relationship(back_populates="commentaries")


class WorldCupQuizSet(Base):
    __tablename__ = "world_cup_quiz_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    image: Mapped[str | None]
    slug: Mapped[str] = mapped_column(unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    start_time: Mapped[datetime | None]
    end_time: Mapped[datetime | None]
    created_by: Mapped[int | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    quizzes: Mapped[list["WorldCupQuiz"]] = relationship(
        back_populates="quiz_set", order_by="WorldCupQuiz.sort_order, WorldCupQuiz.id"
    )


class WorldCupQuiz(Base):
    __tablename__ = "world_cup_quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_cup_quiz_set_id: Mapped[int] = mapped_column(ForeignKey("world_cup_quiz_sets.id"))
    question: Mapped[str]
    description: Mapped[str | None]
    image: Mapped[str | None]
    duration_seconds: Mapped[int] = mapped_column(SmallInteger, default=30)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    quiz_set: Mapped["WorldCupQuizSet"] = relationship(back_populates="quizzes")
    options: Mapped[list["WorldCupQuizOption"]] = relationship(
        back_populates="quiz", order_by="WorldCupQuizOption.id"
    )


class WorldCupQuizOption(Base):
    __tablename__ = "world_cup_quiz_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_cup_quiz_id: Mapped[int] = mapped_column(ForeignKey("world_cup_quizzes.id"))
    option_text: Mapped[str]
    is_correct: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    quiz: Mapped["WorldCupQuiz"] = relationship(back_populates="options")


class WorldCupQuizParticipation(Base):
    __tablename__ = "world_cup_quiz_participations"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_cup_quiz_set_id: Mapped[int] = mapped_column(ForeignKey("world_cup_quiz_sets.id"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    score: Mapped[int] = mapped_column(SmallInteger, default=0)
    total_questions: Mapped[int] = mapped_column(SmallInteger, default=0)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    def is_completed(self) -> bool:
        return self.completed_at is not None


class WorldCupQuizAnswer(Base):
    __tablename__ = "world_cup_quiz_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_cup_quiz_participation_id: Mapped[int] = mapped_column(
        ForeignKey("world_cup_quiz_participations.id")
    )
    world_cup_quiz_id: Mapped[int] = mapped_column(ForeignKey("world_cup_quizzes.id"))
    world_cup_quiz_option_id: Mapped[int | None] = mapped_column(ForeignKey("world_cup_quiz_options.id"))
    is_correct: Mapped[bool] = mapped_column(default=False)
    timed_out: Mapped[bool] = mapped_column(default=False)
    answered_at: Mapped[datetime | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class WorldCupQuestion(Base):
    __tablename__ = "world_cup_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str]
    description: Mapped[str | None]
    image: Mapped[str | None]
    duration_seconds: Mapped[int] = mapped_column(SmallInteger, default=30)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
    start_date_time: Mapped[datetime | None]
    end_date_time: Mapped[datetime | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    options: Mapped[list["WorldCupQuestionOption"]] = relationship(
        back_populates="question", order_by="WorldCupQuestionOption.id"
    )


class WorldCupQuestionOption(Base):
    __tablename__ = "world_cup_question_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_cup_question_id: Mapped[int] = mapped_column(ForeignKey("world_cup_questions.id"))
    option_text: Mapped[str]
    is_correct: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    question: Mapped["WorldCupQuestion"] = relationship(back_populates="options")


class WorldCupQuestionParticipation(Base):
    __tablename__ = "world_cup_question_participations"

    id: Mapped[int] = mapped_column(primary_key=True)
    world_cup_question_id: Mapped[int] = mapped_column(ForeignKey("world_cup_questions.id"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    world_cup_question_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("world_cup_question_options.id")
    )
    is_correct: Mapped[bool] = mapped_column(default=False)
    submitted_at: Mapped[datetime | None]
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
