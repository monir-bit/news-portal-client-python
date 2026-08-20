from app.core.config import settings


def get_media_url(path: str | None) -> str | None:
    """Mirrors UtilsHelper::GetMediaUrl(). Laravel resolves a relative storage
    path against config('filesystems.default')'s public URL — the default disk
    is `r2`, whose public URL is R2_PUBLIC_URL (a custom domain in front of the
    R2 bucket). Returns None for a falsy path, same as the PHP original."""
    if not path:
        return None
    base = settings.media_base_url
    if not base:
        return path
    return f"{base}/{path.lstrip('/')}"
