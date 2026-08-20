from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    title: Mapped[str | None]
    description: Mapped[str | None]
    keywords: Mapped[list | None] = mapped_column(JSONB)
    og_title: Mapped[str | None]
    og_description: Mapped[str | None]
    og_image: Mapped[str | None]
    canonical_url: Mapped[str | None]
    robots: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    english_name: Mapped[str]
    slug: Mapped[str]
    designation: Mapped[str]
    bio: Mapped[str | None]
    facebook: Mapped[str | None]
    email: Mapped[str | None]
    linkedin_url: Mapped[str | None]
    image: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class AuthorNewsMapping(Base):
    __tablename__ = "author_news_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
