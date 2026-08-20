from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.middleware import ApiCacheHeadersMiddleware
from app.core.rate_limit import limiter
from app.routers import (
    club_member,
    comment_card,
    common,
    election,
    employee,
    epaper,
    epaper_question,
    event_banner,
    geo_location,
    home,
    news,
    page,
    page_seo,
    poll,
    popover_add,
    question,
    sitemap,
    web_story,
    world_cup,
    world_cup_question,
    world_cup_quiz_set,
)

app = FastAPI(title="News Portal API (FastAPI port)")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(ApiCacheHeadersMiddleware)

for r in (
    news.router, home.router, common.router,
    world_cup.router, world_cup_quiz_set.router, world_cup_question.router,
    election.router, epaper.router, epaper_question.router,
    poll.router, question.router, comment_card.router, web_story.router,
    employee.router, page.router, page_seo.router, geo_location.router,
    club_member.router, popover_add.router, event_banner.router, sitemap.router,
):
    app.include_router(r, prefix="/api")


@app.get("/")
async def root():
    return {"message": "FastAPI is working!"}


@app.get("/api/test")
async def test():
    return {"success": True, "message": "API is working"}
