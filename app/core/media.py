from app.core.config import settings


def get_media_url(path: str | None) -> str | None:
    """Mirrors UtilsHelper::GetMediaUrl(). Laravel resolves a relative storage
    path against config('filesystems.default')'s public URL — the default disk
    is `s3`, whose public URL is AWS_URL (falls back to the path-style
    endpoint+bucket when unset). Returns None for a falsy path, same as the
    PHP original."""
    if not path:
        return None
    base = settings.media_base_url
    if not base:
        return path
    return f"{base}/{path.lstrip('/')}"
