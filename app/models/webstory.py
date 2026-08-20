from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.news import News


class WebStory(Base):
    __tablename__ = "web_stories"

    id: Mapped[int] = mapped_column(primary_key=True)
    news_id: Mapped[int | None] = mapped_column(ForeignKey("news.id"))
    hash_key: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    news: Mapped["News | None"] = relationship()
    items: Mapped[list["WebStoryItem"]] = relationship(
        back_populates="web_story", order_by="WebStoryItem.position"
    )


class WebStoryItem(Base):
    __tablename__ = "web_story_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    web_story_id: Mapped[int] = mapped_column(ForeignKey("web_stories.id"))
    title: Mapped[str | None]
    image: Mapped[str]
    position: Mapped[int]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    web_story: Mapped["WebStory"] = relationship(back_populates="items")
