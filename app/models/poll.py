from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import PollPage, str_enum_column
from app.models.base import Base


class Poll(Base):
    __tablename__ = "polls"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str]
    page: Mapped[PollPage] = mapped_column(str_enum_column(PollPage), default=PollPage.HOME)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    starts_at: Mapped[datetime | None]
    ends_at: Mapped[datetime | None]
    created_by: Mapped[int | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    options: Mapped[list["PollOption"]] = relationship(
        back_populates="poll", order_by="PollOption.id"
    )


class PollOption(Base):
    __tablename__ = "poll_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"))
    option_text: Mapped[str]
    initial_votes: Mapped[int] = mapped_column(default=0)
    votes_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    poll: Mapped["Poll"] = relationship(back_populates="options")


class PollVote(Base):
    __tablename__ = "poll_votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[int] = mapped_column(ForeignKey("polls.id"))
    poll_option_id: Mapped[int] = mapped_column(ForeignKey("poll_options.id"))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
