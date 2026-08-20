from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Participant(Base):
    """Shared identity (by phone) across Question / WorldCup Quiz / WorldCup
    Question / Epaper Question participation flows."""

    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    phone: Mapped[str] = mapped_column(unique=True)
    email: Mapped[str | None]
    date_of_birth: Mapped[date | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
