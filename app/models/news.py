from datetime import date, datetime

from sqlalchemy import Boolean, ForeignKey, Table, Column, BigInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import IsShowReporterEnum, str_enum_column
from app.models.base import Base

# Pure pivot tables (no extra columns beyond the FKs + timestamps that any
# in-scope endpoint reads) — modeled as plain Core Tables for `secondary=`.
news_tag_mappings = Table(
    "news_tag_mappings",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("news_id", ForeignKey("news.id"), nullable=False),
    Column("tag_id", ForeignKey("tags.id"), nullable=False),
)

news_timeline_tag = Table(
    "news_timeline_tag",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("news_timeline_id", ForeignKey("news_timelines.id"), nullable=False),
    Column("tag_id", ForeignKey("tags.id"), nullable=False),
)

author_news_mappings_secondary = Table(
    "author_news_mappings",
    Base.metadata,
    Column("id", BigInteger, primary_key=True),
    Column("author_id", ForeignKey("authors.id"), nullable=False),
    Column("news_id", ForeignKey("news.id"), nullable=False),
    extend_existing=True,
)


class News(Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    read_count: Mapped[int] = mapped_column(default=0)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    slug_key: Mapped[str]
    old_hash_key: Mapped[str | None]
    shoulder: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str]
    ticker: Mapped[str | None] = mapped_column(Text)
    sort_description: Mapped[str] = mapped_column(Text)
    image: Mapped[str | None]
    image_caption: Mapped[str | None]
    representative: Mapped[str | None]
    is_show_reporter: Mapped[IsShowReporterEnum | None] = mapped_column(str_enum_column(IsShowReporterEnum))
    published: Mapped[bool] = mapped_column(default=False)
    latest: Mapped[bool] = mapped_column(default=False)
    news_marquee: Mapped[bool] = mapped_column(default=False)
    live_news: Mapped[bool] = mapped_column(default=False)
    is_thread: Mapped[bool] = mapped_column(default=False)
    is_visible_shoulder: Mapped[bool] = mapped_column(default=True)
    is_visible_ticker: Mapped[bool] = mapped_column(default=True)
    date: Mapped[datetime]
    created_by: Mapped[int | None]
    updated_by: Mapped[int | None]
    is_working: Mapped[bool] = mapped_column(default=False)
    working_by: Mapped[int | None]
    deleted_at: Mapped[datetime | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    category: Mapped["Category"] = relationship()
    details: Mapped["NewsDetails | None"] = relationship(back_populates="news")
    news_seo: Mapped["NewsSeo | None"] = relationship(back_populates="news")
    live_news_row: Mapped["LiveNews | None"] = relationship(back_populates="news")
    thank_news: Mapped["ThankNews | None"] = relationship(back_populates="news")
    news_images: Mapped[list["NewsImage"]] = relationship(
        back_populates="news", order_by="NewsImage.position"
    )
    news_locations: Mapped[list["NewsLocation"]] = relationship(back_populates="news")
    correspondence: Mapped["NewsCorrespondent | None"] = relationship(back_populates="news")
    tags: Mapped[list["Tag"]] = relationship(secondary=news_tag_mappings)
    authors: Mapped[list["Author"]] = relationship(secondary=author_news_mappings_secondary)


class NewsDetails(Base):
    __tablename__ = "news_details"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    pdf_link: Mapped[str | None]
    details: Mapped[str | None] = mapped_column(Text)
    keyword: Mapped[str | None]
    video_link: Mapped[str | None] = mapped_column(Text)
    video_iframe: Mapped[str | None] = mapped_column(Text)
    video_source: Mapped[str | None]
    is_video_in_thumbnail: Mapped[bool] = mapped_column(default=False)
    google_drive_link: Mapped[str | None] = mapped_column(Text)
    audio_link: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship(back_populates="details")


class NewsImage(Base):
    __tablename__ = "news_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    image_path: Mapped[str]
    caption: Mapped[str | None]
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship(back_populates="news_images")


class NewsSeo(Base):
    __tablename__ = "news_seos"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"), unique=True)
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

    news: Mapped["News"] = relationship(back_populates="news_seo")


class NewsTimeline(Base):
    __tablename__ = "news_timelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int]
    created_news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    title: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text)
    image_path: Mapped[str | None]
    image_caption: Mapped[str | None]
    is_publish: Mapped[bool] = mapped_column(default=True)
    date: Mapped[datetime]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    tags: Mapped[list["Tag"]] = relationship(secondary=news_timeline_tag)


class LatestNews(Base):
    __tablename__ = "latest_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"), unique=True)
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class MarqueNews(Base):
    __tablename__ = "marque_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"), unique=True)
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class LiveNews(Base):
    __tablename__ = "live_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    position: Mapped[int]
    title: Mapped[str | None]
    content: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    stopped_at: Mapped[datetime | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship(back_populates="live_news_row")


class BreakingNews(Base):
    __tablename__ = "breaking_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    reporter_id: Mapped[int | None]
    hash: Mapped[str]
    title: Mapped[str]
    published: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News | None"] = relationship()


class LinkedNews(Base):
    __tablename__ = "linked_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    main_news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    linked_news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    position: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    linked_article: Mapped["News"] = relationship(foreign_keys=[linked_news_id])


class NewsActivityHistory(Base):
    __tablename__ = "news_activity_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    user_id: Mapped[int]
    action: Mapped[str]
    snapshot: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class NewsRead(Base):
    __tablename__ = "news_reads"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    visitor_id: Mapped[str | None]
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    read_count: Mapped[int] = mapped_column(default=0)
    read_date: Mapped[date]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class NewsCorrespondent(Base):
    __tablename__ = "news_correspondents"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    name: Mapped[str]
    image: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship(back_populates="correspondence")


class NewsLocation(Base):
    __tablename__ = "news_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    division_id: Mapped[int] = mapped_column(ForeignKey("divisions.id"))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    upazila_id: Mapped[int] = mapped_column(ForeignKey("upazilas.id"))
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship(back_populates="news_locations")
    division: Mapped["Division"] = relationship()
    district: Mapped["District"] = relationship()
    upazila: Mapped["Upazila"] = relationship()


class ThankNews(Base):
    __tablename__ = "thank_news"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int] = mapped_column(ForeignKey("news.id"))
    title: Mapped[str | None]
    image: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News"] = relationship(back_populates="thank_news")


from app.models.category import Category  # noqa: E402
from app.models.tag_author import Tag, Author  # noqa: E402
from app.models.geo import Division, District, Upazila  # noqa: E402
