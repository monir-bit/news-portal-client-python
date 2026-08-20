from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import EventBannerName, str_enum_column
from app.models.base import Base


class PopoverAdd(Base):
    __tablename__ = "popover_adds"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    image: Mapped[str]
    start_time: Mapped[datetime]
    link: Mapped[str | None]
    end_time: Mapped[datetime]
    delay: Mapped[int]
    duration: Mapped[int]
    is_active: Mapped[bool] = mapped_column(default=True)
    width: Mapped[int | None]
    height: Mapped[int | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class EventBanner(Base):
    __tablename__ = "event_banners"

    id: Mapped[int] = mapped_column(primary_key=True)
    banner_name: Mapped[EventBannerName] = mapped_column(str_enum_column(EventBannerName), unique=True)
    mobile_image: Mapped[str | None]
    link: Mapped[str | None]
    desktop_image: Mapped[str | None]
    start_date: Mapped[datetime | None]
    end_date: Mapped[datetime | None]
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
