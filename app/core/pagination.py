"""Keyset ("cursor") pagination helper.

Laravel's `cursorPaginate()` encodes an opaque cursor token from the current
ORDER BY columns' values on the last row of a page. This port does the same
thing conceptually (a base64 JSON token carrying `[datetime_iso, id]`), but the
token's internal format is a NEW implementation detail — it is NOT
byte-compatible with a Laravel-issued cursor token. A frontend switching from
the Laravel API to this one must treat cursor tokens as opaque and get them
from this API's own responses, not carry over old Laravel-issued tokens.

Scope cut (documented in the implementation guide): only forward ("next")
pagination is implemented. `prev`/`prev_cursor` are always `None` in this pass —
every cursor-paginated endpoint in the source app is consumed by infinite-scroll
UIs that only ever page forward, so this covers the real usage pattern; add
backward paging later if a consumer needs it.

Every cursor-paginated endpoint in the source Laravel app orders by a single
datetime-ish column optionally followed by `id` as a tiebreaker. Endpoints that
only specified one ORDER BY column in the source (e.g. `->latest()`) get an
implicit `id DESC` tiebreaker added here for a well-defined, stable cursor —
a minor, documented deviation from ties being merely "whatever the DB returns".
"""

import base64
import json
from datetime import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.core.config import settings


def encode_cursor(dt: datetime, id_value: int) -> str:
    payload = json.dumps([dt.isoformat(), id_value])
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int]:
    padding = "=" * (-len(cursor) % 4)
    payload = base64.urlsafe_b64decode((cursor + padding).encode()).decode()
    dt_str, id_value = json.loads(payload)
    return datetime.fromisoformat(dt_str), id_value


async def keyset_paginate(
    session: AsyncSession,
    stmt: Select,
    datetime_col,
    id_col,
    limit: int,
    cursor: str | None,
) -> tuple[list[Any], str | None]:
    """`stmt` must select a single ORM entity (not a tuple of columns) and must
    NOT already have an ORDER BY / LIMIT applied — this function adds both.
    Returns `(page_rows, next_cursor)`."""
    if cursor:
        cursor_dt, cursor_id = decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                datetime_col < cursor_dt,
                and_(datetime_col == cursor_dt, id_col < cursor_id),
            )
        )
    stmt = stmt.order_by(datetime_col.desc(), id_col.desc()).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().all()
    has_more = len(rows) > limit
    page = list(rows[:limit])
    next_cursor = None
    if has_more and page:
        last = page[-1]
        next_cursor = encode_cursor(getattr(last, datetime_col.key), getattr(last, id_col.key))
    return page, next_cursor


def resolve_base_path(request: Request) -> str:
    """The current request's path with an absolute base in front of it, for
    building pagination links. Prefers `APP_URL` (config) over the request's
    own scheme+host: behind this deployment's reverse proxy, `request.url`
    resolves to the internal bind address (e.g. `127.0.0.1:443`), not the
    public domain, so it can't be trusted here. Falls back to the request's
    own URL only when `APP_URL` isn't configured (e.g. local dev)."""
    if settings.app_url:
        return f"{settings.app_url.rstrip('/')}{request.url.path}"
    return str(request.url.replace(query=None))


def cursor_page_envelope(data: list[Any], next_cursor: str | None, per_page: int, request: Request) -> dict:
    """Mirrors Laravel's automatic cursor-paginator JSON shape closely enough
    for a frontend to consume (`data`/`links`/`meta`), with `prev`/`prev_cursor`
    always null per the scope cut documented above."""
    full_path = resolve_base_path(request)
    next_url = f"{full_path}?cursor={next_cursor}" if next_cursor else None
    return {
        "data": data,
        "links": {"first": None, "last": None, "prev": None, "next": next_url},
        "meta": {
            "path": full_path,
            "per_page": per_page,
            "next_cursor": next_cursor,
            "next_page_url": next_url,
            "prev_cursor": None,
            "prev_page_url": None,
        },
    }
