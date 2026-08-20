from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ElectionParty(Base):
    __tablename__ = "election_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    symbol_image: Mapped[str | None]
    party_symbol: Mapped[str | None]
    party_symbol_text: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class ElectionSeat(Base):
    __tablename__ = "election_seats"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class ElectionResult(Base):
    __tablename__ = "election_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    election_seat_id: Mapped[int] = mapped_column(ForeignKey("election_seats.id"), unique=True)
    election_party_id: Mapped[int] = mapped_column(ForeignKey("election_parties.id"))
    candidate_name: Mapped[str]
    votes_received: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    seat: Mapped["ElectionSeat"] = relationship()
    party: Mapped["ElectionParty"] = relationship()
