from __future__ import annotations
import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from app.data.models import (
    QuotaInfo, TokenBreakdown, TokenStats, UsageSnapshot,
    DailyToken, ProjectStats, ToolUsage, SkillUsage, TaskItem,
    RuntimeScope, estimate_api_value, parse_jsonl_line,
    CLAUDE_PROMPT_PRICES,
)

# Cache for expensive operations
_cache = {}
_cache_timeout = 60  # seconds


def _claude_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".claude"


def _projects_dir() -> Path:
    return _claude_dir() / "projects"


def _tasks_dir() -> Path:
    return _claude_dir() / "tasks"


def _cache_dir() -> Path:
    return Path(os.path.expanduser("~")) / "Library" / "Caches" / "codexU" / "claude-code"


def read_claude_token_history() -> Optional[TokenStats]:
    import time
    cache_key = "claude_token_history"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    projects_path = _projects_dir()
    if not projects_path.exists():
        return None

    today = datetime.now(timezone.utc).date()
    seven_days_ago = today - timedelta(days=7)

    today_bd = TokenBreakdown()
    week_bd = TokenBreakdown()
    cumulative = TokenBreakdown()

    for jsonl_file in projects_path.rglob("*.jsonl"):
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    event = parse_jsonl_line(line)
                    if not event:
                        continue
                    msg = event.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if not usage or not isinstance(usage, dict):
                        continue

                    inp = usage.get("input_tokens", 0) or 0
                    out = usage.get("output_tokens", 0) or 0
                    cached = usage.get("cached_input_tokens", 0) or 0
                    uncached = inp - cached if inp > cached else inp

                    cumulative.uncached_input += uncached
                    cumulative.cached_input += cached
                    cumulative.output += out

                    ts = event.get("timestamp") or event.get("created_at")
                    if ts:
                        try:
                            d = datetime.fromisoformat(
                                str(ts).replace("Z", "+00:00")
                            ).date()
                            if d == today:
                                today_bd.uncached_input += uncached
                                today_bd.cached_input += cached
                                today_bd.output += out
                            if d >= seven_days_ago:
                                week_bd.uncached_input += uncached
                                week_bd.cached_input += cached
                                week_bd.output += out
                        except (ValueError, AttributeError):
                            pass
        except (OSError, json.JSONDecodeError):
            continue

    result = TokenStats(today=today_bd, last_7d=week_bd, cumulative=cumulative)
    _cache[cache_key] = (time.time(), result)
    return result


def read_claude_quota_snapshot() -> Optional[tuple[QuotaInfo, QuotaInfo]]:
    cache_path = _cache_dir() / "statusline-snapshot.json"
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        limits_5h = data.get("rateLimits", {}).get("5h", {})
        limits_7d = data.get("rateLimits", {}).get("7d", {})

        quota_5h = None
        if "used" in limits_5h and "max" in limits_5h:
            used = limits_5h["used"]
            max_v = limits_5h["max"]
            if max_v > 0:
                used_pct = used / max_v * 100
                quota_5h = QuotaInfo(
                    used_pct=used_pct,
                    remaining_pct=100 - used_pct,
                )

        quota_7d = None
        if "used" in limits_7d and "max" in limits_7d:
            used = limits_7d["used"]
            max_v = limits_7d["max"]
            if max_v > 0:
                used_pct = used / max_v * 100
                quota_7d = QuotaInfo(
                    used_pct=used_pct,
                    remaining_pct=100 - used_pct,
                )

        return (quota_5h, quota_7d)
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def read_claude_projects() -> list[ProjectStats]:
    import time
    cache_key = "claude_projects"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    from collections import defaultdict
    project_tokens: dict[str, int] = defaultdict(int)
    project_threads: dict[str, int] = defaultdict(int)
    project_last: dict[str, Optional[datetime]] = {}

    projects_path = _projects_dir()
    if not projects_path.exists():
        return []

    for jsonl_file in projects_path.rglob("*.jsonl"):
        try:
            mtime = datetime.fromtimestamp(
                jsonl_file.stat().st_mtime, tz=timezone.utc
            )
            parts = jsonl_file.relative_to(projects_path).parts
            project_name = parts[0] if len(parts) > 1 else "default"
            project_threads[project_name] += 1
            if project_name not in project_last or mtime > project_last[project_name]:
                project_last[project_name] = mtime

            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    event = parse_jsonl_line(line)
                    if not event:
                        continue
                    msg = event.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    usage = msg.get("usage")
                    if usage and isinstance(usage, dict):
                        project_tokens[project_name] += (
                            usage.get("input_tokens", 0)
                            + usage.get("output_tokens", 0)
                        )
        except (OSError, json.JSONDecodeError):
            continue

    result = sorted(
        [
            ProjectStats(
                name=name,
                token_total=tokens,
                thread_count=project_threads.get(name, 0),
                last_active=project_last.get(name),
            )
            for name, tokens in project_tokens.items()
        ],
        key=lambda x: x.token_total, reverse=True,
    )
    _cache[cache_key] = (time.time(), result)
    return result


def read_claude_tasks() -> list[TaskItem]:
    import time
    cache_key = "claude_tasks"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    tasks: list[TaskItem] = []
    tasks_path = _tasks_dir()
    if not tasks_path.exists():
        return tasks

    for task_file in tasks_path.rglob("*.json"):
        try:
            with open(task_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            title = data.get("title", data.get("name", task_file.stem))
            status = data.get("status", "pending")
            status_map = {
                "in_progress": "running",
                "pending": "pending",
                "completed": "completed",
                "cancelled": "completed",
            }
            s = status_map.get(status, "pending")
            updated = None
            ts = data.get("updated_at") or data.get("created_at")
            if ts:
                try:
                    updated = datetime.fromisoformat(
                        str(ts).replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass
            tasks.append(TaskItem(
                id=task_file.stem,
                title=title,
                status=s,
                runtime=RuntimeScope.CLAUDE_CODE,
                updated_at=updated,
                project=data.get("project", ""),
            ))
        except (OSError, json.JSONDecodeError, KeyError):
            continue

    _cache[cache_key] = (time.time(), tasks)
    return tasks


def read_claude_tool_usage() -> list[ToolUsage]:
    from collections import defaultdict
    tools: dict[str, int] = defaultdict(int)

    projects_path = _projects_dir()
    if not projects_path.exists():
        return []

    for jsonl_file in projects_path.rglob("*.jsonl"):
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    event = parse_jsonl_line(line)
                    if not event:
                        continue
                    content = event.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                tool_use = block.get("tool_use", {})
                                if isinstance(tool_use, dict):
                                    name = tool_use.get("name", "unknown")
                                    tools[name] += 1
        except (OSError, json.JSONDecodeError):
            continue

    return sorted(
        [ToolUsage(name=n, call_count=c, runtime=RuntimeScope.CLAUDE_CODE)
         for n, c in tools.items()],
        key=lambda x: x.call_count, reverse=True,
    )[:20]


def read_claude_skill_usage() -> list[SkillUsage]:
    skills: dict[str, int] = {}
    projects_path = _projects_dir()
    if not projects_path.exists():
        return []

    for jsonl_file in projects_path.rglob("*.jsonl"):
        try:
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    event = parse_jsonl_line(line)
                    if not event:
                        continue
                    content = event.get("message", {}).get("content", [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict):
                                skill = block.get("skill")
                                if skill and isinstance(skill, str):
                                    skills[skill] = skills.get(skill, 0) + 1
        except (OSError, json.JSONDecodeError):
            continue

    return sorted(
        [SkillUsage(name=n, use_count=c, runtime=RuntimeScope.CLAUDE_CODE)
         for n, c in skills.items()],
        key=lambda x: x.use_count, reverse=True,
    )[:20]


def read_claude_snapshot() -> UsageSnapshot:
    quota = read_claude_quota_snapshot()
    tokens = read_claude_token_history()

    api_value = estimate_api_value(
        tokens.cumulative if tokens else TokenBreakdown(),
        CLAUDE_PROMPT_PRICES,
    ) if tokens else 0.0

    return UsageSnapshot(
        quota_5h=quota[0] if quota else None,
        quota_7d=quota[1] if quota else None,
        tokens=tokens or TokenStats(),
        api_equivalent_value=api_value,
    )
