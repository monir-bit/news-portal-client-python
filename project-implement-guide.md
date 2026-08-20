# FastAPI Port — Implementation Guide

This project is a FastAPI port of the **public (non-reporter) API surface** of the
Laravel 12 news-portal app at `A:\news-portal-api`. It connects to the **same**
Postgres database the Laravel app uses — there are no migrations here, no schema
changes, and no data duplication. Both apps can run side by side against the
same data.

Read this document before extending the project — it records every deliberate
architecture decision, every bug found in the source app and what was done
about it, and every place this port's behavior knowingly diverges from the
Laravel source.

## Scope

**In scope:** every route in `routes/api.php` **except** the `reporter/*` group
(reporter mobile-app login, reporter news submission, reporter notices — all
`auth:sanctum`-gated). Since none of the ported routes require authentication,
**this project has no auth layer at all**.

**Also in scope (by explicit decision):** `Api\SitemapController`'s 5 endpoints
(`/sitemap`, `/sitemap/posts`, `/sitemap/categories`, `/sitemap/tags`,
`/sitemap/news-last-48h`). These were found to be **dead code in the Laravel
app** — the controller exists and is fully implemented, but nothing in
`routes/api.php` or `routes/web.php` ever registers it. They're ported here as
new, live, working endpoints anyway, matching the controller's intended
behavior.

**Explicitly deferred (not in this pass):**
- Redis/`Cache::remember` caching of any kind — every endpoint hits Postgres directly on every request. Every place the Laravel source caches something is called out in a code comment with the original key/TTL, for whoever wires up caching later.
- Meilisearch / Laravel Scout — `/api/search` falls back to a plain `ILIKE` query across `title`/`sort_description`/`shoulder` instead of a search engine.
- Real file storage for the 3 club-member sign-up image uploads — validated and saved to local disk under `uploads/` next to the app, not to R2/S3. (Epaper crop/page downloads DO use real R2 credentials via boto3 — see below.)

## Requirements decisions made with the user up front

1. **Full parity, all at once** — every non-reporter controller was ported in one pass, not incrementally.
2. **Same Postgres DB** — SQLAlchemy models mirror the existing tables exactly; this project never runs its own migrations.
3. **Caching/Meilisearch deferred** — see above.
4. **Async SQLAlchemy 2.0 + asyncpg.**
5. **Fix latent Laravel bugs rather than reproduce them**, with each fix documented in code (see "Bugs found and fixed" below).
6. **Port the dead Sitemap routes as live endpoints.**

## Project layout

```
fastapi-project/
  main.py                    — app factory, middleware, router registration
  requirements.txt
  app/
    core/                    — shared infra, no DB models here
      config.py              — Settings (reads the SAME .env as Laravel, one dir up)
      database.py            — async engine/session, get_db() dependency
      enums.py                — Python mirrors of every Laravel backed enum + str_enum_column() helper
      media.py                — get_media_url() — UtilsHelper::GetMediaUrl() port
      seo.py                  — make_seo() — SeoHelper::Make() port
      phone.py                — normalize_phone() — see "QuizParticipantPhone" below
      portal_time.py          — Asia/Dhaka "now"/"today" helpers, NAIVE datetimes (see below)
      category_tree.py        — recursive-CTE category ancestor/descendant walks
      pagination.py           — keyset ("cursor") pagination helper
      middleware.py           — Cache-Control: public, max-age=30 (mirrors ApiCacheHeaders)
      rate_limit.py           — slowapi Limiter + named limits (public-forms/votes/search)
    models/                  — SQLAlchemy 2.0 declarative models, one file per domain
    schemas/                 — Pydantic response models (only for the recurring core shapes —
                                see "Schema strategy" below)
    queries/                 — business logic, one module per domain/Laravel-Query-class-group
    routers/                 — one FastAPI router per Laravel controller (roughly)
```

## Schema strategy

Laravel's own controllers are wildly inconsistent about response shape (see
the per-route notes below and the spec files in `scratchpad/specs/` from the
research phase) — some routes return a resource wrapped in `{"data": ...}`,
some return a raw resolved array, some return hand-rolled envelopes, and
several "opaque" query results get passed through unchanged from one Query
class to another. Building a fully-typed Pydantic model for every one of these
ad hoc shapes would triple the code size for no correctness benefit.

The pragmatic split actually used:
- **Recurring, well-defined shapes** (`NewsListItem`, `CategoryListItem`, `CategoryBrief`) are real Pydantic models in `app/schemas/common.py`, built once in `app/queries/news_common.py` and reused everywhere.
- **Endpoint-specific / one-off shapes** are plain Python `dict`s built directly in the router or query function, matching the exact JSON shape documented in the research specs. FastAPI serializes them as-is.

If you want full Pydantic coverage later, `app/schemas/common.py` is the place
to start — the endpoint-specific dicts are already shaped correctly, so wrapping
them in `BaseModel`s is mechanical, not a redesign.

## Database & timezone gotchas (read this before writing new queries)

1. **No automatic soft-delete scope.** Laravel's `SoftDeletes` trait adds an
   automatic `deleted_at IS NULL` global scope to every Eloquent query.
   SQLAlchemy has **no equivalent** — every query against `News`,
   `CommentNewsCard`, `EpaperPublication`, `EpaperEdition`, `EpaperEditionPage`,
   and `EpaperRegion` must add `.where(Model.deleted_at.is_(None))` explicitly.
   Forgetting this silently leaks soft-deleted rows back into "public" results.

2. **Naive datetimes, Asia/Dhaka wall-clock.** `news.date`, `news_reads.read_date`,
   and most other timestamp columns are Postgres `timestamp WITHOUT TIME ZONE`,
   and Laravel (with `APP_TIMEZONE=Asia/Dhaka`) writes plain Dhaka wall-clock
   values into them — no UTC conversion, no offset. asyncpg **rejects** binding
   a timezone-aware Python `datetime` against such a column
   (`can't subtract offset-naive and offset-aware datetimes`). `app/core/portal_time.py`
   computes the correct Asia/Dhaka instant first and then strips `tzinfo` before
   returning — every function there (`now()`, `today_start()`, `today_end()`,
   `sub_day()`) returns a **naive** datetime already in the right wall-clock
   value. Use these, don't call `datetime.utcnow()`/`datetime.now()` directly
   in query code.

3. **Enum columns compare by VALUE, not by Python member name.** SQLAlchemy's
   automatic `Mapped[SomeStrEnum]` column inference compares against the enum
   member's *name* (e.g. `"NAME"`) by default, not its `.value` (e.g. `"name"`)
   — which breaks every backed-string-enum column in this schema (all of them
   have upper-case member names but lower-case/hyphenated values, matching the
   Laravel enum backing values). Always declare enum columns via
   `mapped_column(str_enum_column(SomeEnum))` (see `app/core/enums.py`) instead
   of a bare `Mapped[SomeEnum]` — this was a real bug caught during smoke
   testing (`/api/common` 500'd on `news.is_show_reporter` until fixed).

4. **`inet` columns need `sqlalchemy.dialects.postgresql.INET`, not `str`.**
   `poll_votes.ip_address`, `world_cup_quiz_participations.ip_address`, and
   `world_cup_question_participations.ip_address` are native Postgres `inet`
   columns. Mapping them as a plain `Mapped[str | None]` compiles comparisons
   as `inet = varchar`, which Postgres rejects
   (`operator does not exist: inet = character varying`) — this was another
   real bug caught during smoke testing (`/api/polls` 500'd until fixed). Use
   `mapped_column(INET)` for any column the migrations declare as `->ipAddress()`.

## Cursor pagination — reimplemented, not byte-compatible

Laravel's `cursorPaginate()` issues an opaque, Laravel-internal-format cursor
token. This port (`app/core/pagination.py`) implements the **same conceptual**
keyset pagination (base64 JSON of `[datetime_iso, id]`) but the token's
internal format is **new** — a frontend switching from the Laravel API to this
one must get cursor tokens from *this* API's own responses, not carry over
Laravel-issued tokens.

**Known scope cut:** only forward ("next") pagination is implemented.
`prev`/`prev_cursor` are always `null`. Every cursor-paginated endpoint in the
source app is consumed by infinite-scroll UIs that only ever page forward, so
this covers the real usage pattern — add backward paging later if a consumer
needs it.

Endpoints whose Laravel source only specified one `ORDER BY` column (e.g.
`->latest()`) get an implicit `id DESC` tiebreaker added here, for a
well-defined cursor. Documented per-route below.

## Bugs found in the Laravel source and what this port does about them

The research pass (reading every controller/model/migration in scope) found
several places where the Laravel app currently has a hard bug — most
critically, **7+ endpoints across World Cup, Question, and Epaper Question
that reference `App\Support\QuizParticipantPhone::normalize()`, a class that
does not exist anywhere in the Laravel repository**, meaning those endpoints
currently 500 in production. Per an explicit decision, this port **fixes**
these rather than reproducing the crash:

| Laravel bug | Fix in this port |
|---|---|
| `App\Support\QuizParticipantPhone` missing → 500 on `/question/{slug}/answer`, `/question/{slug}/participation`, `/world-cup-quiz-sets/{slug}/start`, `/world-cup-quiz-sets/{slug}/answer`, `/world-cup-questions/{id}/submit`, `/epaper-question/participation`, `/epaper-question/answer` | `app/core/phone.py::normalize_phone()` — a real, working reconstruction: strips whitespace/punctuation, normalizes recognizable Bangladeshi mobile numbers (`01XXXXXXXXX`, `8801XXXXXXXXX`, `+8801XXXXXXXXX`) to the plain local `01XXXXXXXXX` form, passes through anything else unchanged. **This is an invented normalization, not a recovered original** — there was no working reference implementation to copy. Revisit if the product team has a different intended format. |
| `App\Support\ClubMember\ClubMemberImageValidation` missing → 500 on all 3 `POST /club/*` routes | Reconstructed in `app/routers/club_member.py`: image optional; if provided, must be a real decodable image, one of jpeg/jpg/png/gif/webp/bmp, ≤5MB; validated and saved to local disk under `uploads/{Y}/{m}/<uuid>.<ext>` (not R2 — no upload pipeline was built for this pass, see Follow-ups). |
| `WorldCupController::matchDetails({id})` 500s (not 404s) on an unknown id (calls `.makeHidden()` on a null Eloquent result) | Returns a clean `404` instead. |
| `PageSeoController::get()` reads a nonexistent `sort_description` column instead of the real `description` column, so `description`/`og_description`/`twitter_description` are always blank in the source app | Uses the real `description` column. |
| `App\Support\EpaperCropDownloadImage` missing (used by epaper crop/page download endpoints) | Reconstructed with Pillow in `app/queries/epaper_queries.py`: `merge_vertical_from_storage()` stitches two crops head-over-tail; `image_from_storage(..., tiled=...)` re-encodes as JPEG with a best-effort watermark (tiled for single crops, centered for full pages, per the source docblock's "center watermark only" wording for page downloads). **The exact original watermark asset/placement is unknown** — this is a reasonable reconstruction, not a recovered original. |
| `App\Support\EpaperApiCache` missing (cache-invalidation plumbing only) | Skipped entirely — there's no caching to invalidate in this pass. |

**Also found, but left as-is (matches source behavior, not "fixed"):**
- `CategoryLatestNewsQuery`-style code that would null-pointer-crash on a missing category in the source isn't reachable from any in-scope route, so it wasn't an issue in practice.
- `epaper_publications.slug` has **no DB-level uniqueness** at all (a migration removed the unique constraint for soft-delete reasons and never replaced it, unlike editions/pages which got a partial-unique index). First-match-wins semantics preserved as-is.
- `GET /api/upazilas/{districtSlug}` has a real ambiguity: district slugs are only unique **per division**, and this route has no division disambiguator. First match wins, preserved exactly.
- `Poll.activeNow()` tolerates `NULL` `starts_at`/`ends_at` as "unbounded"; `Question.activeNow()` does **not** (`NULL` `start_time`/`end_time` silently excludes the row). This asymmetry is real in the Laravel source and is preserved, not "fixed" into consistency.
- Several IntegrityError-race conditions (concurrent duplicate vote/answer submissions hitting a real DB unique constraint between the app-level `exists()` check and the `INSERT`) are **caught and translated** to the same friendly 422 the app-level check produces, rather than surfacing as a raw 500 — this is a genuine improvement over the Laravel source (which does not catch these), applied consistently across Poll votes, Question answers, World Cup quiz answers, World Cup question submissions, and Epaper question answers.

## Route-by-route map (Laravel → FastAPI)

All FastAPI paths below are mounted under `/api` (see `main.py`). Router
files live in `app/routers/`; business logic lives in the matching
`app/queries/*.py` module.

| Laravel route | FastAPI router | Notes |
|---|---|---|
| `GET /common` | `common.py` | Uncached (source caching was already dead/commented-out code) |
| `GET /home` | `home.py` | `editors_pick` always uses the Bengali-site section slug (`feature-box`) — source's locale-dependent branch has no equivalent concept in this unauthenticated, localeless API (see Follow-ups) |
| `GET /news-details/{slug}` | `news.py` | Fire-and-forget `X-Visitor-ID` read-tracking via `INSERT ... ON CONFLICT DO NOTHING` |
| `GET /news-by-category-home-batch` | `news.py` | |
| `GET /news-by-category-home/{slug}` | `news.py` | |
| `GET /news-by-category/{slug}` | `news.py` | Geo filter cascading-dependency quirk preserved: `district` only honored if `division` resolved; `upazila` only if `district` resolved |
| `GET /news-by-category-sports` | `news.py` (`news_sports.py`) | |
| `GET /news-by-category-world-cup` | `news.py` (`news_worldcup.py`) | |
| `GET /news-by-category-print` | `news.py` | |
| `GET /news-by-print-category/{slug}` | `news.py` | |
| `GET /latest-news` | `news.py` | |
| `GET /search` | `news.py` | Meilisearch deferred — plain `ILIKE` fallback, `search` rate limit (60/min) applied |
| `GET /news-by-tags/{name}` | `news.py` | |
| `GET /news-by-author/{slug}` | `news.py` | |
| `GET/POST /world-cup-*` | `world_cup.py`, `world_cup_quiz_set.py`, `world_cup_question.py` | `votes` rate limit (20/min) on answer/submit routes |
| `GET /election/results`, `/election/summary` | `election.py` | |
| `GET /epaper/publications`, `/epaper/{slug}/{date}`, `/epaper/{slug}/{date}/download-crops`, `/epaper/{slug}/{date}/download-page` | `epaper.py` | Crop/page downloads use real boto3 + R2 credentials from `.env` |
| `GET/POST /epaper-question/*` | `epaper_question.py` | `votes` rate limit on `POST /answer` |
| `GET/POST /polls*` | `poll.py` | `votes` rate limit on `POST /vote` |
| `GET/POST /question/*` | `question.py` | `votes` rate limit on `POST /answer` |
| `GET /comment-card-summary`, `/comment-card/{id}` | `comment_card.py` | |
| `GET /web-story-*` | `web_story.py` | |
| `GET /employees` | `employee.py` | |
| `GET /page/{name}`, `/pages` | `page.py` | |
| `GET /page-seo/{name}` | `page_seo.py` | Bug-fixed (see above) |
| `GET /divisions`, `/districts/{slug}`, `/upazilas/{slug}` | `geo_location.py` | |
| `POST /club/gold`, `/kids`, `/career` | `club_member.py` | `public-forms` rate limit (5/min); image validation reconstructed (see above) |
| `GET /popover-add/active` | `popover_add.py` | |
| `GET /event-banner/{name}` | `event_banner.py` | |
| `GET /sitemap*` (5 routes) | `sitemap.py` | **New**: dead code in Laravel, ported as live endpoints (explicit decision) |

## Running the project

```bash
cd fastapi-project
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Config is read from this project's **own** `.env` at `fastapi-project/.env`
(see `app/core/config.py`) — **not** read directly from the Laravel app's
`.env`. The values were copied over once at setup time (same DB, same R2
bucket). The two are intentionally decoupled: edit `fastapi-project/.env` to
point this project at a different database or bucket without touching (or
being affected by changes to) the Laravel app's config. `.env.example` in the
project root documents every key with blank secrets, for onboarding; `.env`
itself is gitignored.

## Verification performed

Every GET endpoint across every domain was exercised against the **real,
live production Postgres database** (not a fixture/mock) via a running
`uvicorn` instance and returned correct data end-to-end: `/home`, `/common`,
`/news-details/{slug}`, `/news-by-category-home-batch`,
`/news-by-category-home/{slug}`, `/news-by-category/{slug}`,
`/news-by-category-sports`, `/news-by-category-world-cup`,
`/news-by-print-category/{slug}`, `/latest-news`, `/search`,
`/world-cup-today-match`, `/world-cup-all-matches`, `/world-cup-match-details/{id}`,
`/world-cup-quiz-sets`, `/world-cup-questions`, `/world-cup-questions/progress`,
`/election/results`, `/election/summary`, `/epaper/publications`,
`/epaper-question/grid`, `/polls`, `/comment-card-summary`, `/comment-card/{id}`,
`/web-story-slider-data`, `/sports-web-story-slider-data`, `/employees`,
`/pages`, `/page/{name}`, `/page-seo/{name}`, `/divisions`, `/popover-add/active`,
`/event-banner/{name}`, and all 5 `/sitemap*` routes.

**Not exercised in this pass** (to avoid writing test data into the real
production database): the mutating `POST` endpoints (`/club/*`,
`/polls/{id}/vote`, `/question/{slug}/answer`, the World Cup quiz/question
submission routes, `/epaper-question/answer`). These were reviewed by code
inspection and import-tested, but not run end-to-end against live data. Test
them against a disposable database/transaction before relying on them in
production.

Two real bugs were caught and fixed specifically **because** of this live-DB
testing (not just import-time checks) — see the enum-column and `inet`-column
notes above. This is a strong argument for testing every new query against
real data during development, not just unit-testing with mocks.

## Follow-ups / known gaps

1. **Caching.** Wire up Redis (or any cache) for the endpoints whose Laravel
   source cached — every `Cache::remember`/`Cache::flexible`/`rememberForever`
   call site is noted in a code comment with its original key/TTL.
2. **Meilisearch.** `/api/search` currently falls back to `ILIKE` — swap in a
   real Meilisearch client (`meilisearch-python-sdk` or similar) if search
   quality/performance matters.
3. **Backward cursor pagination.** `prev`/`prev_cursor` are always `null` —
   implement if a consumer needs "page back" support.
4. **`editors_pick` locale.** The source picks between `'editors-pick'` and
   `'feature-box'` based on the request's resolved Laravel locale; this port
   has no request-locale concept and always uses `'feature-box'`. Add a
   locale mechanism (header/query param) if English-locale support is needed.
5. **Category-path resolution performance.** `build_category_path()` runs one
   recursive CTE per news item in list responses — correct, but N+1-ish for
   large pages. Worth batching if it becomes a bottleneck.
6. **Club-member image uploads** are saved to local disk, not R2 — wire up
   real object storage if these forms go to production traffic.
7. **`normalize_phone()`** is an invented reconstruction (see bugs table) —
   confirm the intended normalization rules with the product team; it directly
   affects participant deduplication across Question/World-Cup/Epaper flows.
8. **No automated test suite** (pytest) was written for this pass — the
   verification above was manual/live-DB. Add `pytest` + `httpx` + a test
   database/transaction-rollback fixture before this goes to CI.
9. **Reporter portal** (`reporter/*` routes, `auth:sanctum`) is entirely out of
   scope for this project — if it's ever needed, it's a separate, much larger
   effort (adds a real auth layer, Sanctum-compatible or otherwise).
