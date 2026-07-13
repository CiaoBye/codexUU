from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from app.data.models import (
    QuotaInfo, TokenBreakdown, TokenStats, UsageSnapshot,
    DailyToken, ProjectStats, ToolUsage, SkillUsage, TaskItem,
    RuntimeScope, estimate_api_value, parse_jsonl_line,
    CODEX_PROMPT_PRICES,
)

# Cache for expensive operations
_cache = {}
_cache_timeout = 60  # seconds


def _codex_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".codex"


def _state_db_path() -> Optional[Path]:
    p = _codex_dir() / "state_5.sqlite"
    return p if p.exists() else None


def _sessions_dir() -> Path:
    return _codex_dir() / "sessions"


def _archived_sessions_dir() -> Path:
    return _codex_dir() / "archived_sessions"


def _automations_dir() -> Path:
    return _codex_dir() / "automations"


def read_quota_from_appserver() -> Optional[tuple[QuotaInfo, QuotaInfo]]:
    import subprocess
    import shutil
    # Skip if codex command not found
    if not shutil.which("codex"):
        return None
    try:
        result = subprocess.run(
            ["codex", "app-server", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        rate_limits = data.get("account", {}).get("rateLimits", {})
        limits_5h = rate_limits.get("5h", {})
        limits_7d = rate_limits.get("7d", {})

        quota_5h = None
        if "used" in limits_5h and "max" in limits_5h:
            used = limits_5h["used"]
            max_v = limits_5h["max"]
            if max_v > 0:
                used_pct = used / max_v * 100
                quota_5h = QuotaInfo(
                    used_pct=used_pct,
                    remaining_pct=100 - used_pct,
                    reset_time=_parse_reset(limits_5h.get("resetsAt")),
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
                    reset_time=_parse_reset(limits_7d.get("resetsAt")),
                )

        return (quota_5h, quota_7d)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
        return None


def _parse_reset(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone()
    except (ValueError, AttributeError):
        return None


def read_token_totals_from_db() -> Optional[TokenStats]:
    db_path = _state_db_path()
    if not db_path:
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, input_tokens, cached_input_tokens, output_tokens "
            "FROM daily_token_usage ORDER BY date"
        )
        rows = cursor.fetchall()
        conn.close()

        today = datetime.now(timezone.utc).date()
        seven_days_ago = today - timedelta(days=7)

        today_bd = TokenBreakdown()
        week_bd = TokenBreakdown()
        cumulative = TokenBreakdown()

        for row in rows:
            date_str, inp, cached, out = row
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue
            inp = inp or 0
            cached = cached or 0
            out = out or 0
            uncached = inp - cached

            cumulative.uncached_input += uncached
            cumulative.cached_input += cached
            cumulative.output += out

            if d == today:
                today_bd.uncached_input += uncached
                today_bd.cached_input += cached
                today_bd.output += out

            if d >= seven_days_ago:
                week_bd.uncached_input += uncached
                week_bd.cached_input += cached
                week_bd.output += out

        return TokenStats(today=today_bd, last_7d=week_bd, cumulative=cumulative)
    except (sqlite3.Error, ValueError):
        return None


def read_session_tokens() -> TokenBreakdown:
    import time
    cache_key = "session_tokens"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    total = TokenBreakdown()
    for session_dir in [_sessions_dir(), _archived_sessions_dir()]:
        if not session_dir.exists():
            continue
        for rollout_file in session_dir.rglob("rollout-*.jsonl"):
            try:
                with open(rollout_file, "r", encoding="utf-8") as f:
                    for line in f:
                        event = parse_jsonl_line(line)
                        if not event:
                            continue
                        tc = event.get("token_count")
                        if tc and isinstance(tc, dict):
                            total.uncached_input += tc.get("uncached_input", 0)
                            total.cached_input += tc.get("cached_input", 0)
                            total.output += tc.get("output", 0)
            except (OSError, json.JSONDecodeError):
                continue

    _cache[cache_key] = (time.time(), total)
    return total


def read_daily_tokens() -> list[DailyToken]:
    import time
    cache_key = "daily_tokens"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    from collections import defaultdict
    daily: dict[str, DailyToken] = defaultdict(
        lambda: DailyToken(date=datetime.now(timezone.utc), total=0)
    )

    for session_dir in [_sessions_dir(), _archived_sessions_dir()]:
        if not session_dir.exists():
            continue
        for rollout_file in session_dir.rglob("rollout-*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(
                    rollout_file.stat().st_mtime, tz=timezone.utc
                )
                date_key = mtime.strftime("%Y-%m-%d")
                if date_key not in daily:
                    daily[date_key] = DailyToken(date=mtime)
                with open(rollout_file, "r", encoding="utf-8") as f:
                    for line in f:
                        event = parse_jsonl_line(line)
                        if not event:
                            continue
                        tc = event.get("token_count")
                        if tc and isinstance(tc, dict):
                            d = daily[date_key]
                            ci = tc.get("cached_input", 0)
                            ui = tc.get("uncached_input", 0)
                            o = tc.get("output", 0)
                            d.cached_input += ci
                            d.uncached_input += ui
                            d.output += o
                            d.total = d.cached_input + d.uncached_input + d.output
            except (OSError, json.JSONDecodeError):
                continue

    result = sorted(daily.values(), key=lambda x: x.date, reverse=True)
    result = result[:180]
    _cache[cache_key] = (time.time(), result)
    return result


def read_task_board() -> list[TaskItem]:
    import time
    cache_key = "task_board"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    tasks: list[TaskItem] = []
    db_path = _state_db_path()
    if db_path:
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, status, updated_at, project "
                "FROM threads WHERE status IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 50"
            )
            for row in cursor.fetchall():
                tid, title, status, updated_at, project = row
                status_map = {
                    "running": "running",
                    "pending": "pending",
                    "scheduled": "scheduled",
                    "completed": "completed",
                }
                s = status_map.get(status, "pending")
                updated = None
                if updated_at:
                    try:
                        updated = datetime.fromisoformat(
                            str(updated_at).replace("Z", "+00:00")
                        )
                    except (ValueError, AttributeError):
                        pass
                tasks.append(TaskItem(
                    id=str(tid), title=title or "Untitled",
                    status=s, runtime=RuntimeScope.CODEX,
                    updated_at=updated, project=project or "",
                ))
            conn.close()
        except sqlite3.Error:
            pass

    # Read automations
    auto_dir = _automations_dir()
    if auto_dir.exists():
        for toml_file in auto_dir.rglob("automation.toml"):
            try:
                with open(toml_file, "r", encoding="utf-8") as f:
                    content = f.read()
                import re
                name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
                enabled = "enabled = true" in content
                if enabled:
                    tasks.append(TaskItem(
                        id=toml_file.stem,
                        title=name_match.group(1) if name_match else toml_file.stem,
                        status="scheduled",
                        runtime=RuntimeScope.CODEX,
                    ))
            except (OSError, UnicodeDecodeError):
                continue

    _cache[cache_key] = (time.time(), tasks)
    return tasks


def read_projects() -> list[ProjectStats]:
    import time
    cache_key = "projects"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    from collections import defaultdict
    project_tokens: dict[str, int] = defaultdict(int)
    project_threads: dict[str, int] = defaultdict(int)
    project_last: dict[str, Optional[datetime]] = {}

    for session_dir in [_sessions_dir(), _archived_sessions_dir()]:
        if not session_dir.exists():
            continue
        for rollout_file in session_dir.rglob("rollout-*.jsonl"):
            try:
                mtime = datetime.fromtimestamp(
                    rollout_file.stat().st_mtime, tz=timezone.utc
                )
                parts = rollout_file.relative_to(session_dir).parts
                project_name = parts[0] if len(parts) > 1 else "default"
                project_threads[project_name] += 1
                if project_name not in project_last or mtime > project_last[project_name]:
                    project_last[project_name] = mtime

                with open(rollout_file, "r", encoding="utf-8") as f:
                    for line in f:
                        event = parse_jsonl_line(line)
                        if not event:
                            continue
                        tc = event.get("token_count")
                        if tc and isinstance(tc, dict):
                            project_tokens[project_name] += (
                                tc.get("cached_input", 0)
                                + tc.get("uncached_input", 0)
                                + tc.get("output", 0)
                            )
            except (OSError, json.JSONDecodeError):
                continue

    results = []
    for name, tokens in sorted(
        project_tokens.items(), key=lambda x: x[1], reverse=True
    ):
        results.append(ProjectStats(
            name=name,
            token_total=tokens,
            estimated_value=estimate_api_value(
                TokenBreakdown(
                    uncached_input=tokens,
                )
            ),
            thread_count=project_threads.get(name, 0),
            last_active=project_last.get(name),
        ))

    _cache[cache_key] = (time.time(), results)
    return results


def read_tool_usage() -> list[ToolUsage]:
    import time
    cache_key = "tool_usage"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    from collections import defaultdict
    tools: dict[str, int] = defaultdict(int)
    for session_dir in [_sessions_dir(), _archived_sessions_dir()]:
        if not session_dir.exists():
            continue
        for rollout_file in session_dir.rglob("rollout-*.jsonl"):
            try:
                with open(rollout_file, "r", encoding="utf-8") as f:
                    for line in f:
                        event = parse_jsonl_line(line)
                        if not event:
                            continue
                        tool_calls = event.get("tool_calls", [])
                        if isinstance(tool_calls, list):
                            for tc in tool_calls:
                                name = tc.get("name", "unknown") if isinstance(tc, dict) else str(tc)
                                tools[name] += 1
            except (OSError, json.JSONDecodeError):
                continue

    result = sorted(
        [ToolUsage(name=n, call_count=c) for n, c in tools.items()],
        key=lambda x: x.call_count, reverse=True,
    )[:20]
    _cache[cache_key] = (time.time(), result)
    return result


def read_skill_usage() -> list[SkillUsage]:
    import time
    cache_key = "skill_usage"
    if cache_key in _cache:
        cached_time, cached_data = _cache[cache_key]
        if time.time() - cached_time < _cache_timeout:
            return cached_data

    from collections import defaultdict
    skills: dict[str, int] = defaultdict(int)
    for session_dir in [_sessions_dir(), _archived_sessions_dir()]:
        if not session_dir.exists():
            continue
        for rollout_file in session_dir.rglob("rollout-*.jsonl"):
            try:
                with open(rollout_file, "r", encoding="utf-8") as f:
                    for line in f:
                        event = parse_jsonl_line(line)
                        if not event:
                            continue
                        skill = event.get("skill")
                        if skill and isinstance(skill, str):
                            skills[skill] += 1
            except (OSError, json.JSONDecodeError):
                continue

    result = sorted(
        [SkillUsage(name=n, use_count=c) for n, c in skills.items()],
        key=lambda x: x.use_count, reverse=True,
    )[:20]
    _cache[cache_key] = (time.time(), result)
    return result


def read_codex_snapshot() -> UsageSnapshot:
    quota = read_quota_from_appserver()
    tokens = read_token_totals_from_db()
    session_tokens = read_session_tokens()

    if tokens:
        if session_tokens.total > 0 and tokens.cumulative.total == 0:
            tokens.cumulative = session_tokens
    else:
        tokens = TokenStats(
            today=TokenBreakdown(),
            last_7d=TokenBreakdown(),
            cumulative=session_tokens,
        )

    api_value = estimate_api_value(tokens.cumulative, CODEX_PROMPT_PRICES)

    return UsageSnapshot(
        quota_5h=quota[0] if quota else None,
        quota_7d=quota[1] if quota else None,
        tokens=tokens,
        api_equivalent_value=api_value,
    )
