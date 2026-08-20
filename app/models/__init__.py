"""Importing this package registers every mapped class on `Base`'s registry so
that string-based `relationship()` references resolve correctly across modules.
This project never creates/drops tables — it only ever queries the SAME Postgres
database the Laravel app already migrates."""

from app.models.base import Base  # noqa: F401
from app.models import (  # noqa: F401
    category,
    tag_author,
    geo,
    news,
    layout,
    special,
    misc_content,
    participant,
    poll,
    question,
    webstory,
    election,
    epaper,
    worldcup,
    employee,
    static_page,
    club_member,
    banner,
)
