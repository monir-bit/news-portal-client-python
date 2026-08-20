"""Mirrors `EmployeeController::index()`."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.media import get_media_url
from app.models.employee import Employee

router = APIRouter(tags=["employee"])


@router.get("/employees")
async def list_employees(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(
            Employee.full_name,
            Employee.department,
            Employee.nick_name,
            Employee.designation,
            Employee.photo,
        )
        # department_position IS NULL asc, department_position asc,
        # position IS NULL asc, position asc, id asc — NULLs pushed last on
        # both position columns, exactly mirroring the source's raw orderBy.
        .order_by(
            Employee.department_position.is_(None),
            Employee.department_position,
            Employee.position.is_(None),
            Employee.position,
            Employee.id,
        )
    )
    rows = (await db.execute(stmt)).all()

    # Mirrors EmployeeController::index()'s ->groupBy('department'): a PHP
    # Collection groupBy applied AFTER fetch (NOT a SQL GROUP BY). Group keys
    # follow first-appearance order in the already-sorted result set; a
    # null/blank department groups under the literal empty-string key "" —
    # Eloquent's groupBy() behavior for a null grouping value.
    grouped: dict[str, list[dict]] = {}
    for full_name, department, nick_name, designation, photo in rows:
        key = department or ""
        grouped.setdefault(key, []).append({
            "full_name": full_name,
            "department": department,
            "nick_name": nick_name,
            "designation": designation,
            "photo": photo,
            "photo_url": get_media_url(photo),
        })
    return grouped
