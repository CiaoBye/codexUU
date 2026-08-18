from __future__ import annotations
import re
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Optional

WEEKDAY_MAP = {"SU": 1, "MO": 2, "TU": 3, "WE": 4, "TH": 5, "FR": 6, "SA": 7}
CN_WEEKDAY = {1: "日", 2: "一", 3: "二", 4: "三", 5: "四", 6: "五", 7: "六"}


def _normalize_datetime(value: datetime, default_timezone: tzinfo) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=default_timezone)
    return value


def parse_rrule(rrule_text: str) -> dict:
    fields = {}
    for part in rrule_text.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        fields[k.upper()] = v
    return fields


def parse_dtstart(dtstart_line: str) -> tuple[Optional[timezone], Optional[datetime]]:
    if not dtstart_line or ":" not in dtstart_line:
        return None, None
    prefix, value = dtstart_line.split(":", 1)
    tz_match = re.search(r"TZID=([^:]+)", prefix, re.IGNORECASE)
    tz = None
    if tz_match:
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(tz_match.group(1))
        except (ValueError, KeyError, AttributeError, ImportError):
            pass
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            if tz:
                dt = dt.replace(tzinfo=tz)
            return tz, dt
        except ValueError:
            continue
    return tz, None


WEEKDAY_D = WEEKDAY_MAP


def compute_next_run(rrule: str, now: Optional[datetime] = None) -> tuple[str, Optional[datetime]]:
    if not rrule or not rrule.strip():
        return "", None
    now = now or datetime.now()
    lines = [l.strip() for l in rrule.split("\n") if l.strip()]
    fields = {}
    start_date = None
    tz = None
    for line in lines:
        if line.upper().startswith("DTSTART"):
            tz, start_date = parse_dtstart(line)
        elif line.upper().startswith("RRULE:"):
            fields = parse_rrule(line[6:])
        elif "FREQ=" in line.upper():
            fields = parse_rrule(line)
    freq = fields.get("FREQ", "")
    interval = int(fields.get("INTERVAL", "1"))
    byday = fields.get("BYDAY", "")
    weekdays = [WEEKDAY_MAP[d] for d in byday.split(",") if d in WEEKDAY_MAP]

    byhour = int(fields.get("BYHOUR", "-1"))
    byminute = int(fields.get("BYMINUTE", "-1"))
    if byhour == -1 or byminute == -1:
        if start_date and start_date.tzinfo:
            byhour = start_date.hour
            byminute = start_date.minute
        else:
            return _summarize_rule(freq, interval, weekdays), None
    if not (0 <= byhour <= 23 and 0 <= byminute <= 59):
        return _summarize_rule(freq, interval, weekdays), None
    tz = tz or timezone.utc
    now = _normalize_datetime(now, tz)
    if start_date:
        start_date = _normalize_datetime(start_date, tz)
    lower = max(now, start_date) if start_date else now
    summary = _summarize_rule(freq, interval, weekdays)
    if freq == "DAILY":
        return summary, _next_daily(lower, tz, byhour, byminute)
    elif freq == "WEEKLY":
        return summary, _next_weekly(lower, tz, byhour, byminute, weekdays)
    return summary, None


def _summarize_rule(freq: str, interval: int, weekdays: list[int]) -> str:
    if freq == "DAILY":
        return f"每 {interval} 天" if interval > 1 else "每天"
    if freq == "WEEKLY":
        if not weekdays:
            return "每周"
        if sorted(weekdays) == [2, 3, 4, 5, 6]:
            return "工作日"
        return "每周" + "".join(CN_WEEKDAY.get(d, "") for d in weekdays)
    if freq == "HOURLY":
        return f"每 {interval} 小时" if interval > 1 else "每小时"
    if freq == "MINUTELY":
        return f"每 {interval} 分钟" if interval > 1 else "每分钟"
    return "定时"


def _next_daily(lower: datetime, tz: tzinfo, hour: int, minute: int) -> Optional[datetime]:
    lower_local = lower.astimezone(tz)
    candidate = lower_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= lower_local:
        candidate += timedelta(days=1)
    return candidate.astimezone(tz)


def _next_weekly(lower: datetime, tz: tzinfo, hour: int, minute: int, weekdays: list[int]) -> Optional[datetime]:
    if not weekdays:
        return None
    lower_local = lower.astimezone(tz)
    current_wd = lower_local.isoweekday() % 7 + 1
    candidates = []
    for wd in weekdays:
        diff = wd - current_wd
        if diff < 0:
            diff += 7
        elif diff == 0:
            same_day = lower_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if same_day <= lower_local:
                diff += 7
        candidate = lower_local + timedelta(days=diff)
        candidate = candidate.replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidates.append(candidate)
    if not candidates:
        return None
    return min(candidates).astimezone(tz)
