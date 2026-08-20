from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Division(Base):
    __tablename__ = "divisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    slug: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    districts: Mapped[list["District"]] = relationship(back_populates="division")


class District(Base):
    __tablename__ = "districts"

    id: Mapped[int] = mapped_column(primary_key=True)
    division_id: Mapped[int] = mapped_column(ForeignKey("divisions.id"))
    name: Mapped[str]
    slug: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    division: Mapped["Division"] = relationship(back_populates="districts")
    upazilas: Mapped[list["Upazila"]] = relationship(back_populates="district")


class Upazila(Base):
    __tablename__ = "upazilas"

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id"))
    name: Mapped[str]
    slug: Mapped[str]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]

    district: Mapped["District"] = relationship(back_populates="upazilas")
