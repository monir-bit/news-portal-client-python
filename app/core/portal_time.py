from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Asia/Dhaka")


def _naive(dt: datetime) -> datetime:
    """`news.date`/`news_reads.read_date` etc. are Postgres `timestamp/date
    WITHOUT TIME ZONE` columns — Laravel (APP_TIMEZONE=Asia/Dhaka) writes plain
    Dhaka wall-clock values into them with no tz offset attached. asyncpg
    rejects binding a tz-aware Python datetime against such a column, so every
    value used in a DB comparison must be stripped of tzinfo AFTER computing
    the correct Asia/Dhaka wall-clock instant."""
    return dt.replace(tzinfo=None)


def now() -> datetime:
    """Mirrors PortalDateHelper::now() — current Asia/Dhaka wall-clock time,
    naive (see `_naive`) so it compares directly against DB columns."""
    return _naive(datetime.now(TIMEZONE))


def today_date_string() -> str:
    """Mirrors PortalDateHelper::todayDateString()."""
    return now().date().isoformat()


def today_start() -> datetime:
    """Mirrors PortalDateHelper::todayStart()."""
    return now().replace(hour=0, minute=0, second=0, microsecond=0)


def today_end() -> datetime:
    """Mirrors PortalDateHelper::todayEnd()."""
    return now().replace(hour=23, minute=59, second=59, microsecond=999999)


def sub_day() -> datetime:
    """Mirrors PortalDateHelper::subDay() — `now - 24h`, a rolling window bound, not calendar-yesterday."""
    return now() - timedelta(days=1)
