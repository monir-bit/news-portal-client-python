from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. All models map onto the SAME Postgres tables the
    Laravel app already uses — this project never runs migrations of its own."""
