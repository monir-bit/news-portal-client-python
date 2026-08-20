"""Mirrors `PopoverAddApiController::active()`."""

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import portal_time
from app.core.database import get_db
from app.core.media import get_media_url
from app.models.banner import PopoverAdd

router = APIRouter(tags=["popover-add"])


def _iso8601(dt: datetime | None) -> str | None:
    """Mirrors Carbon::toIso8601String() (`Y-m-d\\TH:i:sP`, e.g.
    `2026-08-20T10:00:00+06:00`) — distinct from the `...Z` default JSON-cast
    format used elsewhere (see app/routers/page.py). DB timestamps here are
    naive Asia/Dhaka wall-clock values (see app/core/portal_time.py)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=portal_time.TIMEZONE)
    return dt.isoformat()


@router.get("/popover-add/active")
async def active_popover_add(db: AsyncSession = Depends(get_db)):
    now = portal_time.now()
    stmt = (
        select(PopoverAdd)
        .where(
            PopoverAdd.is_active.is_(True),
            PopoverAdd.start_time <= now,
            PopoverAdd.end_time >= now,
        )
        .order_by(PopoverAdd.id.desc())
    )
    popover = (await db.execute(stmt)).scalars().first()
    if popover is None:
        # Deliberate null-object pattern (200, not 404) — matches the source
        # exactly. JSONResponse used for consistency with the "found" branch.
        return JSONResponse(content={"data": None})

    return JSONResponse(content={
        "data": {
            "id": popover.id,
            "title": popover.title,
            "image": get_media_url(popover.image),
            "link": popover.link,
            "start_time": _iso8601(popover.start_time),
            "end_time": _iso8601(popover.end_time),
            "delay": popover.delay,
            "duration": popover.duration,
            "is_active": popover.is_active,
            "width": popover.width,
            "height": popover.height,
        }
    })
