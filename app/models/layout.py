from datetime import date, datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.news import News


class LayoutSection(Base):
    __tablename__ = "layout_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    position: Mapped[int]
    is_enable: Mapped[bool] = mapped_column(default=True)
    max_news: Mapped[int] = mapped_column(default=10)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class LayoutSectionNews(Base):
    __tablename__ = "layout_section_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    layout_section_id: Mapped[int] = mapped_column(ForeignKey("layout_sections.id"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    position: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship()


class CategoryLayout(Base):
    __tablename__ = "category_layouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    position: Mapped[int]
    is_enable: Mapped[bool] = mapped_column(default=True)
    max_news: Mapped[int] = mapped_column(default=10)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class CategoryLayoutNews(Base):
    __tablename__ = "category_layout_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    category_layout_id: Mapped[int] = mapped_column(ForeignKey("category_layouts.id"))
    position: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship()


class CategoryPageLayout(Base):
    __tablename__ = "category_page_layouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str]
    slug: Mapped[str]
    position: Mapped[int]
    is_enable: Mapped[bool] = mapped_column(default=True)
    max_news: Mapped[int] = mapped_column(default=10)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class CategoryPageLayoutNews(Base):
    __tablename__ = "category_page_layout_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_page_layout_id: Mapped[int] = mapped_column(ForeignKey("category_page_layouts.id"))
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    position: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship()


class PageCategoryMap(Base):
    __tablename__ = "page_category_maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    date: Mapped[date]
    position: Mapped[int]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    category: Mapped["Category"] = relationship()


from app.models.category import Category  # noqa: E402
