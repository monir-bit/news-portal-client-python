"""Mirrors `EventBannerApiController::show()`."""

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import portal_time
from app.core.database import get_db
from app.core.enums import EventBannerName
from app.core.media import get_media_url
from app.models.banner import EventBanner

router = APIRouter(tags=["event-banner"])


def _iso8601(dt: datetime | None) -> str | None:
    """Mirrors the source's private formatDateTime() (Carbon::toIso8601String(),
    `Y-m-d\\TH:i:sP`) — same format/semantics as app/routers/popover_add.py."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=portal_time.TIMEZONE)
    return dt.isoformat()


@router.get("/event-banner/{name}")
async def show_event_banner(name: str, db: AsyncSession = Depends(get_db)):
    try:
        banner_name = EventBannerName(name)  # mirrors EventBannerName::tryFrom($name)
    except ValueError:
        return JSONResponse(content={"data": None})

    stmt = select(EventBanner).where(
        EventBanner.banner_name == banner_name, EventBanner.is_active.is_(True)
    )
    banner = (await db.execute(stmt)).scalars().first()
    if banner is None:
        return JSONResponse(content={"data": None})

    now = portal_time.now()
    if banner.start_date is not None and now < banner.start_date:
        return JSONResponse(content={"data": None})  # not yet started
    if banner.end_date is not None and now > banner.end_date:
        return JSONResponse(content={"data": None})  # already ended

    # Checked against the RAW stored paths (mirrors mobile_image_path /
    # desktop_image_path accessors), not the media-URL-rewritten fields —
    # a blank stored path should still count as "no creative to show".
    if not banner.mobile_image and not banner.desktop_image:
        return JSONResponse(content={"data": None})

    return JSONResponse(content={
        "data": {
            "banner_name": banner.banner_name.value,
            "banner_label": banner.banner_name.label,
            "mobile_image": get_media_url(banner.mobile_image),
            "desktop_image": get_media_url(banner.desktop_image),
            "link": banner.link,
            "start_date": _iso8601(banner.start_date),
            "end_date": _iso8601(banner.end_date),
            "is_active": banner.is_active,
        }
    })
