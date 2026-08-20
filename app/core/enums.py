import enum

from sqlalchemy import Enum as SAEnum


def str_enum_column(enum_cls):
    """SQLAlchemy's automatic `Mapped[SomeStrEnum]` column inference compares by
    the Python enum MEMBER NAME (e.g. "NAME") against the DB value by default,
    not the member's `.value` (e.g. "name") — which breaks every backed string
    enum in this project (their member names are UPPER_CASE, their values are
    the actual lower-case/hyphenated Laravel-column strings). This helper forces
    SQLAlchemy to compare/store by `.value` instead, and treats the column as
    plain text (`native_enum=False`) rather than trying to create/match a
    Postgres native enum type — safe for read-only queries against tables whose
    enum-ish columns are plain varchar in Postgres. For `news.is_show_reporter`,
    which genuinely IS a Postgres native enum type, this still works for reads
    since asyncpg returns the underlying text value regardless."""
    return SAEnum(enum_cls, values_callable=lambda obj: [e.value for e in obj], native_enum=False)


class LayoutSectionEnum(str, enum.Enum):
    """Mirrors app/Enums/LayoutSectionEnum.php — home-page layout section slugs."""

    TRENDING_VIDEO_NEWS = "trending-video-news"
    LEAD_NEWS = "lead-news"
    WORLD_CUP_LEAD = "world-cup-lead"
    PIN_NEWS = "pin-news"
    SUB_LEAD_NEWS = "sub-lead-news"
    FEATURE_BOX = "feature-box"
    OPINION = "opinion"
    ADVICE = "advice"
    FACT_CHECK = "fact-check"
    ANALYSIS = "analysis"
    EDITORS_PICK = "editors-pick"


class PollPage(str, enum.Enum):
    """Mirrors app/Enums/PollPage.php."""

    HOME = "home"
    SPORTS = "sports"
    FIFA_WORLD_CUP = "fifa-world-cup-2026"

    @property
    def label(self) -> str:
        return {
            PollPage.HOME: "Home",
            PollPage.SPORTS: "Sports",
            PollPage.FIFA_WORLD_CUP: "FIFA World Cup",
        }[self]


class IsShowReporterEnum(str, enum.Enum):
    """Mirrors app/Applications/Enums/IsShowReporterEnum.php (news.is_show_reporter)."""

    NAME = "name"
    DESIGNATION = "designation"
    NONE = "none"


class PageSeoPageName(str, enum.Enum):
    """Mirrors app/Applications/Enums/PageSeoPageName.php (page_seos.page_name)."""

    HOME = "home"
    LATEST = "latest"
    SEARCH = "search"
    EPAPER = "epaper"
    ABOUT_US = "about_us"
    TERMS_OF_SERVICE = "terms_of_service"
    CONTACT_US = "contact_us"
    PRIVACY_POLICY = "privacy_policy"
    TEAM = "team"
    CAMPAIGN = "campaign"
    CLUB = "club"
    CLUB_CAREER = "club-career"
    CLUB_GOLD = "club-gold"
    CLUB_KIDS = "club-kids"


class EventBannerName(str, enum.Enum):
    """Mirrors app/Applications/Enums/EventBannerName.php (event_banners.banner_name)."""

    TOP_BANNER = "event-banner"

    @property
    def label(self) -> str:
        return {EventBannerName.TOP_BANNER: "Event banner"}[self]


class WorldCupMatchStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    FINISHED = "finished"
    POSTPONED = "postponed"


class EpaperRegionRole(str, enum.Enum):
    HEAD = "head"
    TAIL = "tail"
