"""Mirrors `GeoLocationController::divisions()/districts()/upazilas()`."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.geo import District, Division, Upazila

router = APIRouter(tags=["geo"])


def _not_found(model_name: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"No query results for model [App\\Models\\{model_name}].")


@router.get("/divisions")
async def list_divisions(db: AsyncSession = Depends(get_db)):
    # No Redis/caching this pass — source wraps this in
    # Cache::rememberForever(CacheKey::divisions(), ...); ported as a direct,
    # uncached query per the user's explicit decision.
    stmt = select(Division.name, Division.slug).order_by(Division.name)
    rows = (await db.execute(stmt)).all()
    return [{"name": r.name, "slug": r.slug} for r in rows]


@router.get("/districts/{divisionSlug}")
async def list_districts(divisionSlug: str, db: AsyncSession = Depends(get_db)):
    # No Redis/caching this pass — source wraps this in
    # Cache::rememberForever(CacheKey::districts($divisionSlug), ...).
    division_stmt = select(Division).where(Division.slug == divisionSlug)
    division = (await db.execute(division_stmt)).scalars().first()
    if division is None:
        raise _not_found("Division")

    districts_stmt = (
        select(District.name, District.slug)
        .where(District.division_id == division.id)
        .order_by(District.name)
    )
    rows = (await db.execute(districts_stmt)).all()
    return {
        "division": {"name": division.name, "slug": division.slug},
        "items": [{"name": r.name, "slug": r.slug} for r in rows],
    }


@router.get("/upazilas/{districtSlug}")
async def list_upazilas(districtSlug: str, db: AsyncSession = Depends(get_db)):
    # No Redis/caching this pass — source wraps this in
    # Cache::rememberForever(CacheKey::upazilas($districtSlug), ...).
    district_stmt = (
        select(District)
        .where(District.slug == districtSlug)
        .options(selectinload(District.division))
    )
    district = (await db.execute(district_stmt)).scalars().first()
    if district is None:
        raise _not_found("District")

    # NOTE: district slugs are only unique PER DIVISION
    # (unique(division_id, slug)), not globally — this route has no
    # divisionSlug disambiguator and simply matches the FIRST district row
    # with this slug, same ambiguity risk baked into the Laravel source (see
    # spec section 3.7). Preserved exactly as-is, not silently "fixed".
    upazilas_stmt = (
        select(Upazila.name, Upazila.slug)
        .where(Upazila.district_id == district.id)
        .order_by(Upazila.name)
    )
    rows = (await db.execute(upazilas_stmt)).all()
    return {
        "division": {"name": district.division.name, "slug": district.division.slug},
        "district": {"name": district.name, "slug": district.slug},
        "items": [{"name": r.name, "slug": r.slug} for r in rows],
    }
