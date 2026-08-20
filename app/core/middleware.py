from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ApiCacheHeadersMiddleware(BaseHTTPMiddleware):
    """Mirrors app/Http/Middleware/ApiCacheHeaders.php: any GET/HEAD request under
    /api/* with no Authorization header gets `Cache-Control: public, max-age=30`."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if (
            request.method in ("GET", "HEAD")
            and request.url.path.startswith("/api/")
            and "authorization" not in request.headers
        ):
            response.headers["Cache-Control"] = "public, max-age=30"
        return response
