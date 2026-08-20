"""Port of `App\\Http\\Controllers\\Api\\EpaperReaderController`.

Route order: `download-crops`/`download-page` are declared before the
catch-all `/epaper/{slug}/{date}` — mirroring the source `routes/api.php`
ordering (though FastAPI's routing isn't actually ambiguous here since the
download routes have an extra path segment; kept for parity/readability).
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.queries.epaper_queries import (
    get_crop_download,
    get_page_download,
    get_publications,
    get_reader_show,
    resolve_reader_edition,
)

router = APIRouter(tags=["epaper"])


@router.get("/epaper/publications")
async def epaper_publications(db: AsyncSession = Depends(get_db)):
    return {"publications": await get_publications(db)}


@router.get("/epaper/{slug}/{date}/download-crops")
async def epaper_download_crops(
    slug: str,
    date: str,
    revision: str | None = None,
    head_region_id: str | None = None,
    tail_region_id: str | None = None,
    region_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    _publication, edition = await resolve_reader_edition(db, slug, date, revision)
    binary, suffix = await get_crop_download(
        db,
        edition_id=edition.id,
        head_region_id=head_region_id,
        tail_region_id=tail_region_id,
        region_id=region_id,
    )
    filename = f"epaper-{slug}-{date}-{suffix}.jpg"
    return Response(
        content=binary,
        media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/epaper/{slug}/{date}/download-page")
async def epaper_download_page(
    slug: str,
    date: str,
    page: str | None = None,
    revision: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    _publication, edition = await resolve_reader_edition(db, slug, date, revision)
    binary, page_number = await get_page_download(db, edition_id=edition.id, page_number_raw=page)
    filename = f"epaper-{slug}-{date}-page-{page_number}.jpg"
    return Response(
        content=binary,
        media_type="image/jpeg",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/epaper/{slug}/{date}")
async def epaper_show(slug: str, date: str, revision: str | None = None, db: AsyncSession = Depends(get_db)):
    return await get_reader_show(db, slug, date, revision)
