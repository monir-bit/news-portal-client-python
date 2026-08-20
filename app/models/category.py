from datetime import datetime

from sqlalchemy import ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    position: Mapped[int] = mapped_column(default=0)
    visible: Mapped[bool] = mapped_column(default=True)
    has_page: Mapped[bool] = mapped_column(default=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    parent: Mapped["Category | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", order_by="Category.position"
    )
    category_seo: Mapped["CategorySeo | None"] = relationship(back_populates="category")


class CategorySeo(Base):
    __tablename__ = "category_seos"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), unique=True)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list | None] = mapped_column(JSONB)
    og_title: Mapped[str | None] = mapped_column(Text)
    og_description: Mapped[str | None] = mapped_column(Text)
    og_image: Mapped[str | None] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text)
    robots: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    category: Mapped["Category"] = relationship(back_populates="category_seo")
