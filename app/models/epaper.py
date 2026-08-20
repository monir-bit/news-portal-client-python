from datetime import date, datetime

from sqlalchemy import ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

# NOTE: Eloquent's `SoftDeletes` trait adds an automatic global scope that
# filters `deleted_at IS NULL` on every query. SQLAlchemy has no equivalent —
# every query against these 4 tables MUST add `.where(Model.deleted_at.is_(None))`
# explicitly (done in app/queries/epaper_queries.py), or soft-deleted rows will
# leak back into "public" results.


class EpaperPublication(Base):
    __tablename__ = "epaper_publications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]  # NOT unique at the DB level post-migration (see spec) — do not add a unique= here.
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    deleted_by: Mapped[int | None]

    editions: Mapped[list["EpaperEdition"]] = relationship(back_populates="publication")


class EpaperEdition(Base):
    __tablename__ = "epaper_editions"

    id: Mapped[int] = mapped_column(primary_key=True)
    epaper_publication_id: Mapped[int] = mapped_column(ForeignKey("epaper_publications.id"))
    publication_date: Mapped[date]
    revision: Mapped[int] = mapped_column(default=1)
    title: Mapped[str | None]
    print_issue_ref: Mapped[str | None]
    status: Mapped[str] = mapped_column(default="draft")  # 'published' gates all public reads
    derived_from_edition_id: Mapped[int | None] = mapped_column(ForeignKey("epaper_editions.id"))
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    deleted_by: Mapped[int | None]

    publication: Mapped["EpaperPublication"] = relationship(back_populates="editions")
    pages: Mapped[list["EpaperEditionPage"]] = relationship(
        back_populates="edition", order_by="EpaperEditionPage.page_number"
    )


class EpaperEditionPage(Base):
    __tablename__ = "epaper_edition_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    epaper_edition_id: Mapped[int] = mapped_column(ForeignKey("epaper_editions.id"))
    page_number: Mapped[int]
    image_path: Mapped[str]
    image_width_px: Mapped[int | None]
    image_height_px: Mapped[int | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    deleted_by: Mapped[int | None]

    edition: Mapped["EpaperEdition"] = relationship(back_populates="pages")
    regions: Mapped[list["EpaperRegion"]] = relationship(back_populates="page")


class EpaperRegion(Base):
    __tablename__ = "epaper_regions"

    ROLE_HEAD = "head"
    ROLE_TAIL = "tail"

    id: Mapped[int] = mapped_column(primary_key=True)
    epaper_edition_page_id: Mapped[int] = mapped_column(ForeignKey("epaper_edition_pages.id"))
    role: Mapped[str]  # CHECK role IN ('head','tail') at the DB level (Postgres only)
    title: Mapped[str]
    external_url: Mapped[str | None]
    x_pct: Mapped[float] = mapped_column(Numeric(9, 4))
    y_pct: Mapped[float] = mapped_column(Numeric(9, 4))
    width_pct: Mapped[float] = mapped_column(Numeric(9, 4))
    height_pct: Mapped[float] = mapped_column(Numeric(9, 4))
    crop_image_path: Mapped[str | None]
    editor_temp_key: Mapped[str | None]
    linked_region_id: Mapped[int | None] = mapped_column(ForeignKey("epaper_regions.id"))
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
    deleted_at: Mapped[datetime | None]
    deleted_by: Mapped[int | None]

    page: Mapped["EpaperEditionPage"] = relationship(back_populates="regions")
    news = relationship("News")


class EpaperCategory(Base):
    __tablename__ = "epaper_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class EpaperQuestion(Base):
    __tablename__ = "epaper_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    epaper_category_id: Mapped[int] = mapped_column(ForeignKey("epaper_categories.id"))
    page_number: Mapped[str | None]  # string column, compared via trim() — not an int
    title: Mapped[str]
    # Laravel casts this via a custom DateOnlyCast to avoid tz-shift; a plain
    # Python `date` (no tzinfo) has the same "no drift" property, so no custom
    # type is needed here.
    publish_date: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    options: Mapped[list["EpaperQuestionOption"]] = relationship(
        back_populates="question", order_by="EpaperQuestionOption.id"
    )


class EpaperQuestionOption(Base):
    __tablename__ = "epaper_question_options"

    id: Mapped[int] = mapped_column(primary_key=True)
    epaper_question_id: Mapped[int] = mapped_column(ForeignKey("epaper_questions.id"))
    option_text: Mapped[str]
    is_correct: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    question: Mapped["EpaperQuestion"] = relationship(back_populates="options")


class EpaperQuestionAnswer(Base):
    __tablename__ = "epaper_question_answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    epaper_question_id: Mapped[int] = mapped_column(ForeignKey("epaper_questions.id"))
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"))
    epaper_question_option_id: Mapped[int] = mapped_column(ForeignKey("epaper_question_options.id"))
    is_correct: Mapped[bool]
    answered_at: Mapped[datetime]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
