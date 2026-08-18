from __future__ import annotations

from datetime import date, datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    from dateutil.tz import gettz as _gettz
except ImportError:
    _gettz = None


SYSTEM = "system"
UTC = "utc"
FIXED = "fixed"
DEFAULT_FIXED_ZONE = "Asia/Shanghai"


class StatisticsTimeZone:
    def __init__(self, mode: str = SYSTEM, identifier: str = DEFAULT_FIXED_ZONE):
        self.mode = mode if mode in (SYSTEM, UTC, FIXED) else SYSTEM
        self.identifier = identifier or DEFAULT_FIXED_ZONE

    def tzinfo(self) -> tzinfo:
        if self.mode == UTC:
            return timezone.utc
        if self.mode == FIXED:
            try:
                return ZoneInfo(self.identifier)
            except (ZoneInfoNotFoundError, ValueError):
                if _gettz:
                    fallback = _gettz(self.identifier)
                    if fallback is not None:
                        return fallback
                return timezone.utc
        return datetime.now().astimezone().tzinfo or timezone.utc

    def date_for(self, value: datetime) -> date:
        return self.datetime_for(value).date()

    def datetime_for(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(self.tzinfo())

    def now_date(self) -> date:
        return datetime.now(timezone.utc).astimezone(self.tzinfo()).date()

    def label(self) -> str:
        if self.mode == UTC:
            return "UTC"
        if self.mode == FIXED:
            return self.identifier
        return "System"


_current = StatisticsTimeZone()


def configure_statistics_timezone(mode: str, identifier: str = DEFAULT_FIXED_ZONE) -> StatisticsTimeZone:
    global _current
    _current = StatisticsTimeZone(mode, identifier)
    return _current


def get_statistics_timezone() -> StatisticsTimeZone:
    return _current
