from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.data.models import (
    CLAUDE_PROMPT_PRICES,
    DailyToken,
    ProjectStats,
    QuotaInfo,
    RuntimeScope,
    SkillUsage,
    TaskItem,
    TokenBreakdown,
    TokenStats,
    ToolUsage,
    UsageSnapshot,
    estimate_api_value,
    parse_jsonl_line,
)
from app.utils.statistics_timezone import get_statistics_timezone


_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 60


def _cached(key: str):
    item = _cache.get(key)
    if item and time.time() - item[0] < _CACHE_TTL:
        return item[1]
    return None


def _store(key: str, value):
    _cache[key] = (time.time(), value)
    return value


def _claude_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".claude"


def _projects_dir() -> Path:
    return _claude_dir() / "projects"


def _tasks_dir() -> Path:
    return _claude_dir() / "tasks"


def _cache_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "codexU" / "claude-code"
    return Path(os.path.expanduser("~")) / "Library" / "Caches" / "codexU" / "claude-code"


def read_claude_quota_snapshot() -> Optional[tuple[Optional[QuotaInfo], Optional[QuotaInfo]]]:
    path = _cache_dir() / "statusline-snapshot.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        limits = data.get("rateLimits", {})

        def make_quota(item) -> Optional[QuotaInfo]:
            if not isinstance(item, dict):
                return None
            used = item.get("used")
            maximum = item.get("max")
            if maximum in (None, 0) or used is None:
                return None
            used_pct = max(0.0, min(100.0, float(used) / float(maximum) * 100))
            reset = item.get("resetsAt", item.get("resetAt"))
            reset_time = None
            if reset:
                try:
                    reset_time = datetime.fromisoformat(str(reset).replace("Z", "+00:00")).astimezone()
                except ValueError:
                    pass
            return QuotaInfo(used_pct=used_pct, remaining_pct=100 - used_pct, reset_time=reset_time)

        return make_quota(limits.get("5h")), make_quota(limits.get("7d"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def read_claude_token_history() -> Optional[TokenStats]:
    cached = _cached("token_history")
    if cached is not None:
        return cached
    projects = _projects_dir()
    if not projects.exists():
        return None

    today = get_statistics_timezone().now_date()
    rolling_start = today - timedelta(days=6)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    today_bd, rolling_bd, week_bd = TokenBreakdown(), TokenBreakdown(), TokenBreakdown()
    month_bd, cumulative = TokenBreakdown(), TokenBreakdown()
    for path in projects.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    event = parse_jsonl_line(line)
                    if not event:
                        continue
                    message = event.get("message", {})
                    usage = message.get("usage") if isinstance(message, dict) else None
                    if not isinstance(usage, dict):
                        continue
                    input_tokens = int(usage.get("input_tokens", 0) or 0)
                    cached_input = int(usage.get("cached_input_tokens", 0) or 0)
                    cached_input += int(usage.get("cache_read_input_tokens", 0) or 0)
                    cached_input += int(usage.get("cache_creation_input_tokens", 0) or 0)
                    output = int(usage.get("output_tokens", 0) or 0)
                    breakdown = TokenBreakdown(
                        cached_input=max(0, cached_input),
                        uncached_input=max(0, input_tokens),
                        output=max(0, output),
                    )
                    cumulative.cached_input += breakdown.cached_input
                    cumulative.uncached_input += breakdown.uncached_input
                    cumulative.output += breakdown.output
                    timestamp = event.get("timestamp") or event.get("created_at")
                    try:
                        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                        day = get_statistics_timezone().date_for(parsed)
                    except (TypeError, ValueError):
                        day = get_statistics_timezone().date_for(datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc))
                    if day == today:
                        today_bd.cached_input += breakdown.cached_input
                        today_bd.uncached_input += breakdown.uncached_input
                        today_bd.output += breakdown.output
                    if day >= rolling_start:
                        rolling_bd.cached_input += breakdown.cached_input
                        rolling_bd.uncached_input += breakdown.uncached_input
                        rolling_bd.output += breakdown.output
                    if day >= week_start:
                        week_bd.cached_input += breakdown.cached_input
                        week_bd.uncached_input += breakdown.uncached_input
                        week_bd.output += breakdown.output
                    if day >= month_start:
                        month_bd.cached_input += breakdown.cached_input
                        month_bd.uncached_input += breakdown.uncached_input
                        month_bd.output += breakdown.output
        except (OSError, UnicodeError):
            continue
    return _store("token_history", TokenStats(
        today=today_bd,
        last_7d=rolling_bd,
        current_week=week_bd,
        cumulative=cumulative,
        current_month=month_bd,
    ))


def read_claude_daily_tokens() -> list[DailyToken]:
    """Aggregate Claude transcript usage into the same 180-day shape as Codex."""
    cached = _cached("daily_tokens")
    if cached is not None:
        return cached
    daily: dict[str, DailyToken] = {}
    projects = _projects_dir()
    if not projects.exists():
        return []
    for path in projects.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    event = parse_jsonl_line(line)
                    message = event.get("message", {}) if event else {}
                    usage = message.get("usage") if isinstance(message, dict) else None
                    if not isinstance(usage, dict):
                        continue
                    timestamp = event.get("timestamp") or event.get("created_at")
                    try:
                        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                    except (TypeError, ValueError):
                        parsed = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
                    day = get_statistics_timezone().date_for(parsed)
                    cached_input = int(usage.get("cached_input_tokens", 0) or 0)
                    cached_input += int(usage.get("cache_read_input_tokens", 0) or 0)
                    cached_input += int(usage.get("cache_creation_input_tokens", 0) or 0)
                    breakdown = TokenBreakdown(
                        cached_input=max(0, cached_input),
                        uncached_input=max(0, int(usage.get("input_tokens", 0) or 0)),
                        output=max(0, int(usage.get("output_tokens", 0) or 0)),
                    )
                    key = day.isoformat()
                    item = daily.setdefault(
                        key,
                        DailyToken(
                            date=datetime.combine(day, datetime.min.time(), tzinfo=get_statistics_timezone().tzinfo()),
                            runtime=RuntimeScope.CLAUDE_CODE,
                        ),
                    )
                    item.cached_input += breakdown.cached_input
                    item.uncached_input += breakdown.uncached_input
                    item.output += breakdown.output
                    item.total = item.cached_input + item.uncached_input + item.output
        except (OSError, UnicodeError):
            continue
    result = sorted(daily.values(), key=lambda item: item.date, reverse=True)[:180]
    return _store("daily_tokens", result)


def read_claude_tasks() -> list[TaskItem]:
    cached = _cached("tasks")
    if cached is not None:
        return cached
    result: list[TaskItem] = []
    tasks_dir = _tasks_dir()
    if not tasks_dir.exists():
        return result
    for path in tasks_dir.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            status = str(data.get("status", "pending"))
            status = {"in_progress": "running", "pending": "pending", "completed": "completed", "cancelled": "completed"}.get(status, "pending")
            timestamp = data.get("updated_at") or data.get("created_at")
            updated = None
            if timestamp:
                try:
                    updated = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                except ValueError:
                    pass
            result.append(TaskItem(
                id=path.stem,
                title=data.get("title", data.get("name", path.stem)),
                status=status,
                runtime=RuntimeScope.CLAUDE_CODE,
                updated_at=updated,
                project=data.get("project", ""),
            ))
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError):
            continue
    today = get_statistics_timezone().now_date()
    result = [
        task for task in result
        if task.updated_at is None or get_statistics_timezone().date_for(task.updated_at) == today
    ]
    return _store("tasks", result)


def read_claude_projects() -> list[ProjectStats]:
    cached = _cached("projects")
    if cached is not None:
        return cached
    data = defaultdict(lambda: {
        "tokens": 0, "threads": 0, "last": None,
        "breakdown": TokenBreakdown(), "recent": TokenBreakdown(),
        "week": TokenBreakdown(), "month": TokenBreakdown(),
    })
    today = get_statistics_timezone().now_date()
    recent_start = today - timedelta(days=6)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    projects = _projects_dir()
    if not projects.exists():
        return []
    for path in projects.rglob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            parts = path.relative_to(projects).parts
            name = parts[0] if len(parts) > 1 else "default"
            data[name]["threads"] += 1
            if data[name]["last"] is None or mtime > data[name]["last"]:
                data[name]["last"] = mtime
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    event = parse_jsonl_line(line)
                    message = event.get("message", {}) if event else {}
                    usage = message.get("usage") if isinstance(message, dict) else None
                    if isinstance(usage, dict):
                        cached_input = int(usage.get("cached_input_tokens", 0) or 0)
                        cached_input += int(usage.get("cache_read_input_tokens", 0) or 0)
                        cached_input += int(usage.get("cache_creation_input_tokens", 0) or 0)
                        breakdown = TokenBreakdown(
                            cached_input=max(0, cached_input),
                            uncached_input=max(0, int(usage.get("input_tokens", 0) or 0)),
                            output=max(0, int(usage.get("output_tokens", 0) or 0)),
                        )
                        data[name]["tokens"] += breakdown.total
                        for field in ("cached_input", "uncached_input", "output"):
                            data[name]["breakdown"].__dict__[field] += getattr(breakdown, field)
                        timestamp = event.get("timestamp") or event.get("created_at")
                        try:
                            event_day = get_statistics_timezone().date_for(datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")))
                        except (TypeError, ValueError):
                            event_day = get_statistics_timezone().date_for(mtime)
                        if event_day >= recent_start:
                            for field in ("cached_input", "uncached_input", "output"):
                                data[name]["recent"].__dict__[field] += getattr(breakdown, field)
                        if week_start <= event_day <= today:
                            for field in ("cached_input", "uncached_input", "output"):
                                data[name]["week"].__dict__[field] += getattr(breakdown, field)
                        if month_start <= event_day <= today:
                            for field in ("cached_input", "uncached_input", "output"):
                                data[name]["month"].__dict__[field] += getattr(breakdown, field)
        except (OSError, UnicodeError):
            continue
    result = [
        ProjectStats(
            name=name,
            token_total=item["tokens"],
            estimated_value=estimate_api_value(item["breakdown"], CLAUDE_PROMPT_PRICES),
            thread_count=item["threads"],
            last_active=item["last"],
            runtime=RuntimeScope.CLAUDE_CODE,
            last_7d_token_total=item["recent"].total,
            last_7d_estimated_value=estimate_api_value(item["recent"], CLAUDE_PROMPT_PRICES),
            current_week_token_total=item["week"].total,
            current_week_estimated_value=estimate_api_value(item["week"], CLAUDE_PROMPT_PRICES),
            current_week_pricing_coverage_pct=100.0 if item["week"].total else 0.0,
            current_month_token_total=item["month"].total,
            current_month_estimated_value=estimate_api_value(item["month"], CLAUDE_PROMPT_PRICES),
            current_month_pricing_coverage_pct=100.0 if item["month"].total else 0.0,
            pricing_coverage_pct=100.0 if item["tokens"] else 0.0,
            source_label="精细统计",
        )
        for name, item in data.items()
    ]
    result.sort(key=lambda item: item.token_total, reverse=True)
    return _store("projects", result[:20])


def _content_blocks(event: dict):
    message = event.get("message", {})
    content = message.get("content", []) if isinstance(message, dict) else []
    return content if isinstance(content, list) else []


def read_claude_tool_usage() -> list[ToolUsage]:
    counts: defaultdict[str, int] = defaultdict(int)
    projects = _projects_dir()
    if not projects.exists():
        return []
    for path in projects.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    event = parse_jsonl_line(line)
                    if not event:
                        continue
                    for block in _content_blocks(event):
                        if isinstance(block, dict):
                            tool_use = block.get("tool_use")
                            if isinstance(tool_use, dict) and isinstance(tool_use.get("name"), str):
                                counts[tool_use["name"]] += 1
        except (OSError, UnicodeError):
            continue
    def category(name: str) -> str:
        lowered = name.lower()
        if any(token in lowered for token in ("bash", "terminal", "shell", "exec")):
            return "命令执行"
        if any(token in lowered for token in ("read", "write", "edit", "glob", "grep")):
            return "文件操作"
        if any(token in lowered for token in ("web", "search", "fetch")):
            return "网络访问"
        return "其他"

    return sorted(
        [ToolUsage(
            name=name,
            call_count=count,
            runtime=RuntimeScope.CLAUDE_CODE,
            category=category(name),
        ) for name, count in counts.items()],
        key=lambda item: item.call_count,
        reverse=True,
    )


def read_claude_skill_usage() -> list[SkillUsage]:
    counts: defaultdict[str, int] = defaultdict(int)
    projects = _projects_dir()
    if not projects.exists():
        return []
    for path in projects.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    event = parse_jsonl_line(line)
                    for block in _content_blocks(event or {}):
                        if isinstance(block, dict) and isinstance(block.get("skill"), str):
                            counts[block["skill"]] += 1
        except (OSError, UnicodeError):
            continue
    return sorted(
        [SkillUsage(name=name, use_count=count, runtime=RuntimeScope.CLAUDE_CODE) for name, count in counts.items()],
        key=lambda item: item.use_count,
        reverse=True,
    )


def read_claude_snapshot() -> UsageSnapshot:
    quota = read_claude_quota_snapshot()
    tokens = read_claude_token_history() or TokenStats()
    return UsageSnapshot(
        quota_5h=quota[0] if quota else None,
        quota_7d=quota[1] if quota else None,
        tokens=tokens,
        api_equivalent_value=estimate_api_value(tokens.cumulative, CLAUDE_PROMPT_PRICES),
        today_api_equivalent_value=estimate_api_value(tokens.today, CLAUDE_PROMPT_PRICES),
        last_7d_api_equivalent_value=estimate_api_value(tokens.last_7d, CLAUDE_PROMPT_PRICES),
        current_week_api_equivalent_value=estimate_api_value(tokens.current_week, CLAUDE_PROMPT_PRICES),
        monthly_api_equivalent_value=estimate_api_value(tokens.current_month, CLAUDE_PROMPT_PRICES),
        pricing_coverage_pct=100.0 if tokens.cumulative.total else 0.0,
    )
