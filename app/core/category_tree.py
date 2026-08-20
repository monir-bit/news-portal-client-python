"""Category tree helpers — Python replacements for Category::childrenRecursive /
parentRecursive (unbounded recursive Eloquent relations) and the Query classes
that walk them (CategoryAllChildrenIdsQuery, CategoryIdsByChildRecursiveQuery).

SQLAlchemy has no equivalent of Eloquent's lazy recursive relation, so every one
of these is a `WITH RECURSIVE` CTE against categories(id, parent_id, slug) —
see scratchpad/specs/applications_helpers.md section "Recursive category logic"
for why three different semantics exist and must not be conflated.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def build_category_path(session: AsyncSession, category_id: int) -> str:
    """Mirrors CategoryPathService::build($category) — '/'-joined slugs from the
    root ancestor down to (and including) `category_id`, no leading/trailing slash."""
    sql = text(
        """
        WITH RECURSIVE ancestors AS (
            SELECT id, parent_id, slug, 0 AS depth FROM categories WHERE id = :category_id
            UNION ALL
            SELECT c.id, c.parent_id, c.slug, a.depth + 1
            FROM categories c JOIN ancestors a ON c.id = a.parent_id
        )
        SELECT slug FROM ancestors ORDER BY depth DESC
        """
    )
    result = await session.execute(sql, {"category_id": category_id})
    return "/".join(row[0] for row in result.fetchall())


async def descendant_ids_by_slug(session: AsyncSession, slug: str) -> list[int]:
    """Mirrors CategoryAllChildrenIdsQuery::handle($slug): full-depth descendant
    walk (all levels) of the category matching `slug`, PLUS the category's own id
    appended last. Returns [] if no category has that slug (matches the PHP,
    which returns [] rather than erroring on an unknown slug)."""
    sql = text(
        """
        WITH RECURSIVE root AS (
            SELECT id FROM categories WHERE slug = :slug
        ), descendants AS (
            SELECT id FROM root
            UNION ALL
            SELECT c.id FROM categories c JOIN descendants d ON c.parent_id = d.id
        )
        SELECT id FROM descendants
        """
    )
    result = await session.execute(sql, {"slug": slug})
    ids = [row[0] for row in result.fetchall()]
    if not ids:
        return []
    # Root id must sort last, to mirror getAllChildIds()'s DFS-then-self-last order
    # (call sites only use this as a membership/whereIn set, so order is otherwise inert).
    root_sql = text("SELECT id FROM categories WHERE slug = :slug")
    root_id = (await session.execute(root_sql, {"slug": slug})).scalar_one()
    return [i for i in ids if i != root_id] + [root_id]


async def self_and_direct_children_ids(session: AsyncSession, slugs: list[str]) -> list[int]:
    """Mirrors CategoryIdsByChildRecursiveQuery::handle($slugs): for EACH matched
    slug, includes the category's own id PLUS its DIRECT children only (NOT the
    full subtree, despite the name/relation looking recursive — see spec notes).
    Duplicates are possible (not deduped), matching the PHP."""
    if not slugs:
        return []
    sql = text(
        """
        SELECT c.id AS self_id, child.id AS child_id
        FROM categories c
        LEFT JOIN categories child ON child.parent_id = c.id
        WHERE c.slug = ANY(:slugs)
        """
    )
    rows = (await session.execute(sql, {"slugs": slugs})).fetchall()
    ids: list[int] = []
    seen_self: set[int] = set()
    for self_id, child_id in rows:
        if self_id not in seen_self:
            ids.append(self_id)
            seen_self.add(self_id)
        if child_id is not None:
            ids.append(child_id)
    return ids
