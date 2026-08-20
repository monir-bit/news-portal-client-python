"""Mirrors `PageSeoController::get()`."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import PageSeoPageName
from app.core.media import get_media_url
from app.core.seo import make_seo
from app.models.static_page import PageSeo

router = APIRouter(tags=["page-seo"])


@router.get("/page-seo/{name}")
async def get_page_seo(name: str, db: AsyncSession = Depends(get_db)):
    try:
        page_name = PageSeoPageName(name)
    except ValueError:
        # The source queries `PageSeo::where('page_name', $name)` with the raw
        # route string, unvalidated against the enum, then calls firstOrFail().
        # Since the DB column only ever contains valid enum-value strings, an
        # unrecognized `name` can never match a row anyway — converting here
        # first (rather than binding an arbitrary string against a typed enum
        # column) reaches the identical outcome: 404, "not found".
        raise HTTPException(
            status_code=404,
            detail="No query results for model [App\\Models\\PageSeo].",
        )

    stmt = select(PageSeo).where(PageSeo.page_name == page_name)
    seo = (await db.execute(stmt)).scalars().first()
    if seo is None:
        raise HTTPException(
            status_code=404,
            detail="No query results for model [App\\Models\\PageSeo].",
        )

    # BUG FIX (per explicit user decision — see spec section 3.4): the Laravel
    # source reads `$seo->sort_description`, a column/attribute that does not
    # exist on `PageSeo` (the real column is `description`). Eloquent silently
    # resolves an undefined attribute read to null instead of erroring, so in
    # the committed source `description`/`og_description`/`twitter_description`
    # were ALWAYS blank regardless of the actual `description` column value.
    # This port uses the real `description` column, fixing the bug.
    return make_seo(
        title=seo.title,
        image=get_media_url(seo.og_image),
        description=seo.description,
        keywords=seo.keywords,
    )
