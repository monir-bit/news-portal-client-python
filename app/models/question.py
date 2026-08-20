from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    title: Mapped[str]
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    start_time: Mapped[datetime | None]
    end_time: Mapped[datetime | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    options: Mapped[list["QuestionOption"]] = relationship(
        back_populates="question", order_by="QuestionOption.id"
    )


class QuestionOption(Base):
    __tablename__ = "question_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    option_text: Mapped[str]
    is_correct: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    question: Mapped["Question"] = relationship(back_populates="options")


class QuestionAnswer(Base):
    __tablename__ = "question_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    question_option_id: Mapped[int] = mapped_column(ForeignKey("question_options.id"))
    is_correct: Mapped[bool]
    answered_at: Mapped[datetime]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
