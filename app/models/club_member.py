from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GoldClubMember(Base):
    __tablename__ = "gold_club_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int | None]
    image: Mapped[str | None]
    gender: Mapped[str | None]  # 'male' | 'female' | 'others'
    profession: Mapped[str | None]
    blood_group: Mapped[str | None]
    hobby: Mapped[str | None]
    address: Mapped[str | None]
    phone: Mapped[str | None]
    email: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class KidsClubMember(Base):
    __tablename__ = "kids_club_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int | None]
    image: Mapped[str | None]
    gender: Mapped[str | None]
    school_or_madrasa: Mapped[str | None]
    blood_group: Mapped[str | None]
    hobby: Mapped[str | None]
    address: Mapped[str | None]
    guardian_phone: Mapped[str | None]
    email: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]


class CareerClubMember(Base):
    __tablename__ = "career_club_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    age: Mapped[int | None]
    image: Mapped[str | None]
    gender: Mapped[str | None]
    educational_qualification: Mapped[str | None]
    preferred_profession: Mapped[str | None]
    work_experience: Mapped[str | None]
    address: Mapped[str | None]
    phone: Mapped[str | None]
    email: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
