from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.news import News
from app.models.tag_author import Tag


class SpecialSegment(Base):
    __tablename__ = "special_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))
    slug: Mapped[str]
    desktop_banner_image: Mapped[str | None]
    mobile_banner_image: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    tag: Mapped["Tag"] = relationship()


class SpecialSegmentNews(Base):
    __tablename__ = "special_segment_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    special_segment_id: Mapped[int] = mapped_column(ForeignKey("special_segments.id"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship()


class SpecialTag(Base):
    __tablename__ = "special_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class SpecialTagNews(Base):
    __tablename__ = "special_tag_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    special_tag_id: Mapped[int] = mapped_column(ForeignKey("special_tags.id"))
    position: Mapped[int]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship()
    special_tag: Mapped["SpecialTag"] = relationship()
