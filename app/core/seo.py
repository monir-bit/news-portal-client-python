from app.core.config import settings


def limit_at_word_boundary(text: str | None, limit: int = 160) -> str:
    """Mirrors SeoHelper::limitAtWordBoundary(). Trims text; if it already fits,
    returns as-is; otherwise hard-cuts at `limit` chars and backs off to the last
    space boundary (if one exists past position 0) to avoid cutting mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    last_space = cut.rfind(" ")
    if last_space > 0:
        return cut[:last_space]
    return cut


def make_seo(
    title: str | None = None,
    image: str | None = None,
    description: str | None = None,
    keywords: list[str] | None = None,
) -> dict:
    """Mirrors SeoHelper::Make() (app/Applications/Helpers/SeoHelper.php) field-for-field."""
    desc = limit_at_word_boundary(description or "")
    return {
        "title": title or "",
        "description": desc,
        "keywords": ",".join(keywords) if keywords else "",
        "og_title": title,
        "og_description": desc,
        "og_image": image,
        "og_type": "article",
        "og_site_name": settings.app_name,
        "twitter_card": "summary_large_image",
        "twitter_title": title,
        "twitter_description": desc,
        "twitter_image": image,
    }
