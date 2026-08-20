"""Mirrors `PageController::show()` / `PageController::index()`."""

from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.static_page import StaticPage

router = APIRouter(tags=["page"])


def _laravel_json_datetime(dt: datetime | None) -> str | None:
    """Mirrors Eloquent's default Carbon JSON-cast format (`Y-m-d\\TH:i:s.u\\Z`)
    used for `StaticPage.updated_at` here — a literal `Z` suffix appended to the
    naive Asia/Dhaka wall-clock value (NOT an actual UTC conversion; this is
    Laravel's well-known default-timezone serialization quirk when
    APP_TIMEZONE != UTC). Distinct from the `Carbon::toIso8601String()` offset
    format used elsewhere in this domain (popover-add/event-banner/sitemap)."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


@router.get("/page/{name}")
async def show_page(name: str, db: AsyncSession = Depends(get_db)):
    stmt = select(StaticPage).where(StaticPage.name == name)
    page = (await db.execute(stmt)).scalars().first()
    if page is None:
        # Custom-built body (source builds this manually, NOT the generic
        # Laravel ModelNotFoundException shape) — {"data": null, "message":
        # "Page not found"} has two flat top-level keys, so JSONResponse is
        # used to avoid HTTPException's default `detail`-nesting.
        return JSONResponse(status_code=404, content={"data": None, "message": "Page not found"})
    return {"data": {"id": page.id, "name": page.name, "content": page.content}}


@router.get("/pages")
async def list_pages(db: AsyncSession = Depends(get_db)):
    stmt = select(StaticPage.id, StaticPage.name, StaticPage.updated_at)
    rows = (await db.execute(stmt)).all()
    return {
        "data": [
            {"id": r.id, "name": r.name, "updated_at": _laravel_json_datetime(r.updated_at)}
            for r in rows
        ]
    }
