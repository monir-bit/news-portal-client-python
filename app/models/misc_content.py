from datetime import date, datetime, time

from sqlalchemy import ForeignKey, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.news import News


class CommentNewsCard(Base):
    __tablename__ = "comment_news_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    image: Mapped[str | None]
    short_description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0)
    date: Mapped[date]
    is_publish: Mapped[bool] = mapped_column(default=False)
    commenter: Mapped[str | None] = mapped_column(Text)
    commenter_image: Mapped[str | None]
    comment: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None]
    updated_by: Mapped[int | None]
    deleted_by: Mapped[int | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News | None"] = relationship()


class SourceLine(Base):
    __tablename__ = "source_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class Caption(Base):
    __tablename__ = "captions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class CardAddGallery(Base):
    __tablename__ = "card_add_galleries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    image: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class MediaGallery(Base):
    __tablename__ = "media_galleries"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    media_type: Mapped[str] = mapped_column(default="image")
    path: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class RamadanSchedule(Base):
    __tablename__ = "ramadan_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    ramadan_day: Mapped[int] = mapped_column(SmallInteger)
    date: Mapped[date]
    sehri_end: Mapped[time]
    iftar_time: Mapped[time]
    fajr: Mapped[time | None]
    iftar_azan: Mapped[time | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
