from datetime import datetime

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import PageSeoPageName, str_enum_column
from app.models.base import Base


class StaticPage(Base):
    __tablename__ = "static_pages"

    ALLOWED_NAMES = ("terms", "about", "contact", "privacy")

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    content: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class PageSeo(Base):
    __tablename__ = "page_seos"

    id: Mapped[int] = mapped_column(primary_key=True)
    page_name: Mapped[PageSeoPageName] = mapped_column(str_enum_column(PageSeoPageName), unique=True)
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
