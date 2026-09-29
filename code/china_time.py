"""China time that still works when the frozen app has no timezone database."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CHINA_OFFSET = timezone(timedelta(hours=8))


def china_zone():
    try:
        return ZoneInfo("Asia/Shanghai")
    except Exception:
        return CHINA_OFFSET


CHINA_TIME = china_zone()


def china_now() -> datetime:
    return datetime.now(CHINA_TIME)
