from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_no: Mapped[str | None] = mapped_column(unique=True)
    position: Mapped[int | None]
    full_name: Mapped[str]
    nick_name: Mapped[str | None]
    designation: Mapped[str]
    mobile_no: Mapped[str] = mapped_column(unique=True)
    desk_no: Mapped[str | None]
    department: Mapped[str | None]
    department_position: Mapped[int | None]
    beat: Mapped[str | None]
    blood_group: Mapped[str | None]
    joining_date: Mapped[date | None]
    present_address: Mapped[str | None]
    permanent_address: Mapped[str | None]
    photo: Mapped[str | None]
    created_at: Mapped[datetime | None]
    updated_at: Mapped[datetime | None]
