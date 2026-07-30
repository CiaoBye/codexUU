from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from queue import Empty, Queue
from threading import Thread
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.data.models import (
    DailyToken,
    ModelUsage,
    ProjectStats,
    QuotaInfo,
    RuntimeScope,
    SkillUsage,
    SessionUsage,
    TaskItem,
    TokenBreakdown,
    TokenStats,
    ToolUsage,
    UsageSnapshot,
    QUOTA_STATUS_AVAILABLE,
    QUOTA_STATUS_EXHAUSTED,
    QUOTA_STATUS_UNAVAILABLE,
    estimate_model_api_value,
    parse_jsonl_line,
)
from app.utils.statistics_timezone import get_statistics_timezone
from app.constants import APP_VERSION


_cache: dict[str, tuple[float, object]] = {}
_CACHE_TTL = 60
_rollout_file_cache: dict[Path, tuple[int, int, datetime, list[dict]]] = {}
_ROLLOUT_FILE_CACHE_LIMIT = 1024
_last_quota_status = QUOTA_STATUS_UNAVAILABLE
# Spawning the Desktop-managed standalone runtime for every 60-second token
# refresh can make Codex repeatedly recycle that helper process.  Keep a
# successfully verified live quota briefly; session/token aggregation still
# refreshes on every cycle.
_LIVE_QUOTA_TTL_SECONDS = 300
_live_quota_cache: Optional[tuple[float, tuple[Optional[QuotaInfo], Optional[QuotaInfo]], str]] = None


def _cached(key: str):
    item = _cache.get(key)
    if item and time.time() - item[0] < _CACHE_TTL:
        return item[1]
    return None


def _store(key: str, value):
    _cache[key] = (time.time(), value)
    return value


def clear_cache():
    """清除聚合快照；保留 rollout 文件级缓存，避免重复解析未变化日志。"""
    global _last_quota_status
    _cache.clear()
    _last_quota_status = QUOTA_STATUS_UNAVAILABLE


def _codex_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".codex"


def _state_db_path() -> Optional[Path]:
    for path in (_codex_dir() / "state_5.sqlite", _codex_dir() / "sqlite" / "state_5.sqlite"):
        if path.exists():
            return path
    return None


def _connect_state_db(path: Path):
    """Open Codex state without creating or mutating its database."""
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=1)


def _sessions_dir() -> Path:
    return _codex_dir() / "sessions"


def _archived_dir() -> Path:
    return _codex_dir() / "archived_sessions"


def _automations_dir() -> Path:
    return _codex_dir() / "automations"


def _parse_reset(value) -> Optional[datetime]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc).astimezone()
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except (TypeError, ValueError, OverflowError):
        return None


def _set_quota_status(status: str):
    global _last_quota_status
    _last_quota_status = status


def get_last_quota_status() -> str:
    """Return the status produced by the most recent quota read."""
    return _last_quota_status


def _status_from_rate_limits(
    limits: object,
    quota: tuple[Optional[QuotaInfo], Optional[QuotaInfo]],
) -> str:
    if any(quota):
        return QUOTA_STATUS_AVAILABLE
    # The Codex rollout schema keeps the limit id but clears both windows when
    # the account has exhausted its allowance.  Treat only this explicit
    # shape as exhausted; an absent/malformed object remains unverifiable.
    if (
        isinstance(limits, dict)
        and limits.get("limit_id", limits.get("limitId")) == "codex"
        and "primary" in limits
        and "secondary" in limits
        and limits.get("primary") is None
        and limits.get("secondary") is None
    ):
        return QUOTA_STATUS_EXHAUSTED
    return QUOTA_STATUS_UNAVAILABLE


def _appserver_executables() -> list[str]:
    """Return usable standalone Codex CLIs, excluding the Store execution alias.

    The Store alias is discoverable through PATH but cannot consistently spawn
    a stdio app-server.  Codex Desktop also keeps an independent runtime under
    ``~/.codex``; prefer it when present so quota reads can ask the backend for
    the current reset timestamp instead of relying only on persisted events.
    """
    candidates: list[str] = []
    resolved = shutil.which("codex")
    if resolved:
        candidates.append(resolved)
    codex_dir = _codex_dir()
    candidates.extend([
        str(codex_dir / ".sandbox-bin" / "codex.exe"),
        str(codex_dir / "plugins" / ".plugin-appserver" / "codex.exe"),
    ])
    seen: set[str] = set()
    usable: list[str] = []
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen or (os.name == "nt" and "windowsapps" in normalized):
            continue
        seen.add(normalized)
        if os.path.isfile(candidate):
            usable.append(candidate)
    return usable


def _appserver_rate_limits(executable: str) -> Optional[dict]:
    """Read one current rate-limit response without closing app-server early."""
    process = None
    response_lines: Queue[str] = Queue()

    def consume_stdout(stream):
        try:
            for line in stream:
                response_lines.put(line)
        finally:
            stream.close()

    try:
        process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        if process.stdin is None or process.stdout is None:
            return None
        reader = Thread(target=consume_stdout, args=(process.stdout,), daemon=True)
        reader.start()

        def send(message: dict):
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()

        send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"clientInfo": {"name": "CodexUU", "version": APP_VERSION.lstrip("v")}},
        })
        deadline = time.monotonic() + 3.0
        initialized = False
        while time.monotonic() < deadline:
            try:
                message = json.loads(response_lines.get(timeout=0.15))
            except Empty:
                continue
            except json.JSONDecodeError:
                continue
            if message.get("id") == 1 and "result" in message:
                initialized = True
                break
        if not initialized:
            return None

        send({"jsonrpc": "2.0", "method": "initialized", "params": {}})
        # Current protocol defines this request with null params.  Empty object
        # worked in older builds but is rejected by newer app-server versions.
        send({"jsonrpc": "2.0", "id": 2, "method": "account/rateLimits/read", "params": None})
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                message = json.loads(response_lines.get(timeout=0.15))
            except Empty:
                continue
            except json.JSONDecodeError:
                continue
            if message.get("id") == 2 and isinstance(message.get("result"), dict):
                return message["result"]
        return None
    except (OSError, subprocess.SubprocessError, TypeError, ValueError):
        return None
    finally:
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
            except OSError:
                pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()


def _codex_rate_limits_from_response(payload: dict) -> dict:
    """Select the Codex bucket from legacy and current app-server responses."""
    buckets = payload.get("rateLimitsByLimitId")
    if isinstance(buckets, dict) and isinstance(buckets.get("codex"), dict):
        return buckets["codex"]
    limits = payload.get("rateLimits")
    if isinstance(limits, dict):
        return limits
    account = payload.get("account")
    if isinstance(account, dict) and isinstance(account.get("rateLimits"), dict):
        return account["rateLimits"]
    return {}


def read_quota_from_appserver() -> Optional[tuple[Optional[QuotaInfo], Optional[QuotaInfo]]]:
    """Read rolling rate limits when the local Codex CLI is available."""
    global _live_quota_cache
    now = time.monotonic()
    if _live_quota_cache is not None:
        checked_at, quota, status = _live_quota_cache
        if now - checked_at < _LIVE_QUOTA_TTL_SECONDS:
            _set_quota_status(status)
            return quota
    for executable in _appserver_executables():
        payload = _appserver_rate_limits(executable)
        if not isinstance(payload, dict):
            continue
        limits = _codex_rate_limits_from_response(payload)
        quota = _quota_pair_from_rate_limits(limits)
        status = _status_from_rate_limits(limits, quota)
        _set_quota_status(status)
        _live_quota_cache = (now, quota, status)
        return quota
    _set_quota_status(QUOTA_STATUS_UNAVAILABLE)
    return None


def _quota_pair_from_rate_limits(limits: dict) -> tuple[Optional[QuotaInfo], Optional[QuotaInfo]]:
    if not isinstance(limits, dict):
        return None, None

    def make_quota(item) -> tuple[Optional[int], Optional[QuotaInfo]]:
        if not isinstance(item, dict):
            return None, None
        used = item.get("used_percent", item.get("usedPercent", item.get("used")))
        maximum = item.get("max", item.get("limit"))
        if maximum not in (None, 0):
            used_pct = float(used or 0) / float(maximum) * 100
        elif used is not None:
            used_pct = float(used)
        else:
            return None, None
        window = item.get("window_minutes", item.get("windowDurationMins"))
        used_pct = max(0.0, min(100.0, used_pct))
        return int(window) if window is not None else None, QuotaInfo(
            used_pct=used_pct,
            remaining_pct=100.0 - used_pct,
            reset_time=_parse_reset(item.get("resets_at", item.get("resetsAt", item.get("resetAt")))),
        )

    q5 = q7 = None
    candidates = []
    for key in ("5h", "7d", "primary", "secondary"):
        if key in limits:
            window, quota = make_quota(limits.get(key))
            if quota is not None:
                candidates.append((key, window, quota))
    for key, window, quota in candidates:
        if key == "5h" or window == 300:
            q5 = quota
        elif key == "7d" or window == 10080:
            q7 = quota
    return q5, q7


def read_quota_from_session_events() -> Optional[tuple[Optional[QuotaInfo], Optional[QuotaInfo]]]:
    """Read the newest persisted Codex rate-limit snapshot without a full history scan."""
    cached = _cached("quota_session_events")
    if cached is not None:
        _set_quota_status(_cached("quota_session_status") or QUOTA_STATUS_UNAVAILABLE)
        return cached
    # The current quota is written into recent token_count events.  Sampling the
    # newest files is both the most current local source available to the Store
    # desktop app and avoids parsing months of unrelated session history.
    for path, mtime, stat in _recent_rollout_files(days=14, limit=32):
        for event in reversed(_read_rollout_file_events(path, stat, mtime)):
            payload = event.get("payload")
            limits = payload.get("rate_limits") if isinstance(payload, dict) else None
            if not isinstance(limits, dict):
                continue
            result = _quota_pair_from_rate_limits(limits)
            status = _status_from_rate_limits(limits, result)
            # A newest event with explicit empty windows is authoritative: do
            # not resurrect an older quota snapshot after a reset or account
            # state change.  Codex uses this empty shape after exhaustion, so
            # preserve the status even though there is no honest window to draw.
            _set_quota_status(status)
            _store("quota_session_status", status)
            return _store("quota_session_events", result)
    _set_quota_status(QUOTA_STATUS_UNAVAILABLE)
    _store("quota_session_status", QUOTA_STATUS_UNAVAILABLE)
    return _store("quota_session_events", None)


def _recent_rollout_files(days: int, limit: int) -> list[tuple[Path, datetime, os.stat_result]]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    candidates: list[tuple[Path, datetime, os.stat_result]] = []
    for root in (_sessions_dir(), _archived_dir()):
        if not root.exists():
            continue
        for path in root.rglob("rollout-*.jsonl"):
            try:
                stat = path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                if mtime >= cutoff:
                    candidates.append((path, mtime, stat))
            except OSError:
                continue
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[:limit]


def _read_rollout_file_events(path: Path, stat: os.stat_result, mtime: datetime) -> list[dict]:
    cached_file = _rollout_file_cache.get(path)
    if cached_file and cached_file[0] == stat.st_mtime_ns and cached_file[1] == stat.st_size:
        return cached_file[3]
    events: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                event = parse_jsonl_line(line)
                if event:
                    events.append(event)
    except (OSError, UnicodeError):
        return []
    _rollout_file_cache[path] = (stat.st_mtime_ns, stat.st_size, mtime, events)
    return events


def _read_token_event(event: dict) -> Optional[tuple[str, TokenBreakdown, bool]]:
    timestamp = event.get("timestamp") or event.get("created_at") or ""
    usage = None
    cumulative = False
    if event.get("type") == "event_msg":
        payload = event.get("payload", {})
        if isinstance(payload, dict) and payload.get("type") == "token_count":
            info = payload.get("info", {}) or {}
            usage = info.get("total_token_usage", info)
            cumulative = "total_token_usage" in info
    if usage is None:
        usage = event.get("token_count")
    if not isinstance(usage, dict):
        return None

    cached = int(usage.get("cached_input_tokens", usage.get("cached_input", 0)) or 0)
    input_tokens = int(usage.get("input_tokens", usage.get("input", 0)) or 0)
    uncached = usage.get("uncached_input")
    if uncached is None:
        uncached = max(0, input_tokens - cached)
    output = int(usage.get("output_tokens", usage.get("output", 0)) or 0)
    return str(timestamp), TokenBreakdown(
        cached_input=max(0, cached),
        uncached_input=max(0, int(uncached or 0)),
        output=max(0, output),
    ), cumulative


def _delta_breakdown(previous: Optional[TokenBreakdown], current: TokenBreakdown) -> TokenBreakdown:
    if previous is None:
        return current

    def delta(old: int, new: int) -> int:
        # A reset or a restarted session starts a new counter at `new`.
        return new - old if new >= old else new

    return TokenBreakdown(
        cached_input=max(0, delta(previous.cached_input, current.cached_input)),
        uncached_input=max(0, delta(previous.uncached_input, current.uncached_input)),
        output=max(0, delta(previous.output, current.output)),
    )


def _event_date(timestamp: str, fallback: datetime) -> datetime:
    if timestamp:
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(get_statistics_timezone().tzinfo())
        except (TypeError, ValueError):
            pass
    return fallback.astimezone(get_statistics_timezone().tzinfo())


def _model_context_from_event(event: dict) -> tuple[str, str, str]:
    """Extract only model metadata needed to attribute subsequent token deltas."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return "", "", ""
    source = payload
    if payload.get("type") == "thread_settings_applied" and isinstance(payload.get("thread_settings"), dict):
        source = payload["thread_settings"]
    model = str(source.get("model") or "").strip()
    effort = str(source.get("effort") or source.get("reasoning_effort") or "").strip().lower()
    if not effort:
        collaboration = source.get("collaboration_mode")
        settings = collaboration.get("settings") if isinstance(collaboration, dict) else None
        if isinstance(settings, dict):
            effort = str(settings.get("reasoning_effort") or "").strip().lower()
    turn_id = str(payload.get("turn_id") or source.get("turn_id") or "").strip()
    return model, effort, turn_id


def _iter_token_deltas(days: Optional[int] = None) -> Iterator[tuple[Path, datetime, str, TokenBreakdown, dict]]:
    cache_key = f"token_deltas:{days if days is not None else 'all'}"
    cached = _cached(cache_key)
    if cached is not None:
        yield from cached
        return
    previous: dict[Path, TokenBreakdown] = {}
    active_models: dict[Path, str] = {}
    active_efforts: dict[Path, str] = {}
    active_turns: dict[Path, str] = {}
    records: list[tuple[Path, datetime, str, TokenBreakdown, dict]] = []
    for path, mtime, event in _iter_rollout_events(days=days):
        model, effort, turn_id = _model_context_from_event(event)
        if model:
            active_models[path] = model
        if effort:
            active_efforts[path] = effort
        if turn_id:
            active_turns[path] = turn_id
        parsed = _read_token_event(event)
        if not parsed:
            continue
        timestamp, current, cumulative = parsed
        delta = _delta_breakdown(previous.get(path), current) if cumulative else current
        if cumulative:
            previous[path] = current
        if delta.total > 0:
            event["_codexu_model"] = active_models.get(path, "")
            event["_codexu_effort"] = active_efforts.get(path, "")
            event["_codexu_turn_id"] = active_turns.get(path, "")
            records.append((path, mtime, timestamp, delta, event))
    _store(cache_key, records)
    yield from records


def _iter_rollout_events(days: Optional[int] = None) -> Iterator[tuple[Path, datetime, dict]]:
    cache_key = f"rollout_events:{days if days is not None else 'all'}"
    cached = _cached(cache_key)
    if cached is not None:
        yield from cached
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days is not None else None
    records: list[tuple[Path, datetime, dict]] = []
    seen_files: set[Path] = set()
    for root in (_sessions_dir(), _archived_dir()):
        if not root.exists():
            continue
        for path in root.rglob("rollout-*.jsonl"):
            try:
                stat = path.stat()
                mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                if cutoff is not None and mtime < cutoff:
                    continue
                seen_files.add(path)
                events = _read_rollout_file_events(path, stat, mtime)
                records.extend((path, mtime, event) for event in events)
            except (OSError, UnicodeError):
                continue
    for stale_path in set(_rollout_file_cache) - seen_files:
        _rollout_file_cache.pop(stale_path, None)
    if len(_rollout_file_cache) > _ROLLOUT_FILE_CACHE_LIMIT:
        keep = {
            path for path, _ in sorted(
                _rollout_file_cache.items(), key=lambda item: item[1][2], reverse=True,
            )[:_ROLLOUT_FILE_CACHE_LIMIT]
        }
        for stale_path in set(_rollout_file_cache) - keep:
            _rollout_file_cache.pop(stale_path, None)
    _store(cache_key, records)
    yield from records


def read_token_totals_from_db() -> Optional[TokenStats]:
    db_path = _state_db_path()
    if not db_path:
        return None
    try:
        with _connect_state_db(db_path) as conn:
            rows = conn.execute(
                "SELECT date, input_tokens, cached_input_tokens, output_tokens "
                "FROM daily_token_usage ORDER BY date"
            ).fetchall()
    except sqlite3.Error:
        return None

    today = get_statistics_timezone().now_date()
    rolling_start = today - timedelta(days=6)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    today_bd, rolling_bd, week_bd = TokenBreakdown(), TokenBreakdown(), TokenBreakdown()
    month_bd, cumulative = TokenBreakdown(), TokenBreakdown()
    for date_value, input_tokens, cached, output in rows:
        try:
            day = datetime.strptime(str(date_value)[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        cached = max(0, int(cached or 0))
        uncached = max(0, int(input_tokens or 0) - cached)
        breakdown = TokenBreakdown(cached_input=cached, uncached_input=uncached, output=int(output or 0))
        cumulative.cached_input += breakdown.cached_input
        cumulative.uncached_input += breakdown.uncached_input
        cumulative.output += breakdown.output
        if day == today:
            today_bd.cached_input += breakdown.cached_input
            today_bd.uncached_input += breakdown.uncached_input
            today_bd.output += breakdown.output
        if rolling_start <= day <= today:
            rolling_bd.cached_input += breakdown.cached_input
            rolling_bd.uncached_input += breakdown.uncached_input
            rolling_bd.output += breakdown.output
        if week_start <= day <= today:
            week_bd.cached_input += breakdown.cached_input
            week_bd.uncached_input += breakdown.uncached_input
            week_bd.output += breakdown.output
        if month_start <= day <= today:
            month_bd.cached_input += breakdown.cached_input
            month_bd.uncached_input += breakdown.uncached_input
            month_bd.output += breakdown.output
    return TokenStats(
        today=today_bd,
        last_7d=rolling_bd,
        current_week=week_bd,
        cumulative=cumulative,
        current_month=month_bd,
    )


def read_thread_index_token_total() -> Optional[int]:
    """Return Codex's own per-thread token index total when the column exists."""
    db_path = _state_db_path()
    if not db_path:
        return None
    try:
        with _connect_state_db(db_path) as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(tokens_used), 0) FROM threads "
                "WHERE tokens_used IS NOT NULL"
            ).fetchone()
    except sqlite3.Error:
        return None
    value = int(row[0] or 0) if row else 0
    return value or None


def read_session_tokens() -> TokenBreakdown:
    cached = _cached("session_tokens")
    if cached is not None:
        return cached
    total = TokenBreakdown()
    for _, _, _, breakdown, _ in _iter_token_deltas():
        total.cached_input += breakdown.cached_input
        total.uncached_input += breakdown.uncached_input
        total.output += breakdown.output
    return _store("session_tokens", total)


def read_daily_tokens() -> list[DailyToken]:
    cached = _cached("daily_tokens")
    if cached is not None:
        return cached
    daily: dict[str, DailyToken] = {}
    for _, mtime, timestamp, breakdown, _ in _iter_token_deltas():
        day = _event_date(timestamp, mtime)
        key = day.strftime("%Y-%m-%d")
        item = daily.setdefault(key, DailyToken(date=day, runtime=RuntimeScope.CODEX))
        item.cached_input += breakdown.cached_input
        item.uncached_input += breakdown.uncached_input
        item.output += breakdown.output
        item.total = item.cached_input + item.uncached_input + item.output
    result = sorted(daily.values(), key=lambda item: item.date, reverse=True)
    return _store("daily_tokens", result)


def read_model_usage() -> list[ModelUsage]:
    cached = _cached("model_usage")
    if cached is not None:
        return cached
    grouped = defaultdict(lambda: {
        "tokens": TokenBreakdown(), "sessions": set(), "turns": set(),
        "last": None, "daily": {}, "session_activity": {}, "turn_activity": {},
    })

    def add(target: TokenBreakdown, value: TokenBreakdown):
        target.cached_input += value.cached_input
        target.uncached_input += value.uncached_input
        target.output += value.output

    for path, mtime, timestamp, breakdown, event in _iter_token_deltas():
        model = str(event.get("_codexu_model") or "").strip()
        effort = str(event.get("_codexu_effort") or "").strip().lower()
        item = grouped[(model, effort)]
        add(item["tokens"], breakdown)
        item["sessions"].add(path)
        turn_id = str(event.get("_codexu_turn_id") or "").strip()
        if turn_id:
            item["turns"].add(turn_id)
        event_time = _event_date(timestamp, mtime)
        session_key = str(path)
        previous_session_time = item["session_activity"].get(session_key)
        if previous_session_time is None or event_time > previous_session_time:
            item["session_activity"][session_key] = event_time
        if turn_id:
            previous_turn_time = item["turn_activity"].get(turn_id)
            if previous_turn_time is None or event_time > previous_turn_time:
                item["turn_activity"][turn_id] = event_time
        if item["last"] is None or event_time > item["last"]:
            item["last"] = event_time
        day_key = event_time.date().isoformat()
        daily = item["daily"].setdefault(
            day_key,
            DailyToken(
                date=datetime.combine(event_time.date(), datetime.min.time(), tzinfo=get_statistics_timezone().tzinfo()),
                runtime=RuntimeScope.CODEX,
            ),
        )
        daily.cached_input += breakdown.cached_input
        daily.uncached_input += breakdown.uncached_input
        daily.output += breakdown.output
        daily.total = daily.cached_input + daily.uncached_input + daily.output

    result = []
    for (model, effort), item in grouped.items():
        tokens = item["tokens"]
        if not tokens.total:
            continue
        value = estimate_model_api_value(tokens, model)
        result.append(ModelUsage(
            name=model or "未知模型",
            effort=effort,
            runtime=RuntimeScope.CODEX,
            token_total=tokens.total,
            tokens=tokens,
            estimated_value=value or 0.0,
            pricing_coverage_pct=100.0 if value is not None else 0.0,
            session_count=len(item["sessions"]),
            turn_count=len(item["turns"]),
            last_active=item["last"],
            daily_tokens=sorted(item["daily"].values(), key=lambda daily: daily.date, reverse=True),
            session_activity=item["session_activity"],
            turn_activity=item["turn_activity"],
        ))
    return _store("model_usage", sorted(result, key=lambda item: item.token_total, reverse=True))


def read_model_priced_values() -> dict[str, float | int]:
    cached = _cached("model_priced_values")
    if cached is not None:
        return cached
    today = get_statistics_timezone().now_date()
    rolling_start = today - timedelta(days=6)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    periods = ("today", "rolling_week", "week", "month", "cumulative")
    grouped = {period: defaultdict(TokenBreakdown) for period in periods}
    priced_tokens = 0
    unpriced_tokens = 0
    for _, mtime, timestamp, breakdown, event in _iter_token_deltas():
        model = str(event.get("_codexu_model") or "")
        if estimate_model_api_value(TokenBreakdown(), model) is None:
            unpriced_tokens += breakdown.total
            continue
        priced_tokens += breakdown.total
        day = _event_date(timestamp, mtime).date()
        active_periods = ["cumulative"]
        if day == today:
            active_periods.append("today")
        if rolling_start <= day <= today:
            active_periods.append("rolling_week")
        if week_start <= day <= today:
            active_periods.append("week")
        if month_start <= day <= today:
            active_periods.append("month")
        for period in active_periods:
            item = grouped[period][model]
            item.cached_input += breakdown.cached_input
            item.uncached_input += breakdown.uncached_input
            item.output += breakdown.output
    values = {
        period: round(sum(
            estimate_model_api_value(tokens, model) or 0.0
            for model, tokens in grouped[period].items()
        ), 2)
        for period in periods
    }
    total = priced_tokens + unpriced_tokens
    values.update({
        "priced_tokens": priced_tokens,
        "unpriced_tokens": unpriced_tokens,
        "coverage_pct": priced_tokens / total * 100 if total else 0.0,
    })
    return _store("model_priced_values", values)


def _parse_updated(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _clean_task_title(value, fallback="未命名任务") -> str:
    text = str(value or fallback)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def _classify_thread_task(archived, created_at, updated_at, recency_at, archived_at, now):
    created = _parse_updated(created_at)
    updated = _parse_updated(updated_at)
    recency = _parse_updated(recency_at)
    archived_time = _parse_updated(archived_at)
    statistics = get_statistics_timezone()
    if bool(archived):
        activity = archived_time or updated
        return ("completed", activity) if activity else None
    today = statistics.date_for(now)
    candidates = [value for value in (created, updated, recency) if value is not None]
    if not candidates or not any(statistics.date_for(value) == today for value in candidates):
        return None
    activity = recency or updated or created
    age = now.astimezone(timezone.utc) - activity.astimezone(timezone.utc)
    return ("running" if age <= timedelta(hours=2) else "pending"), activity


def read_task_board() -> list[TaskItem]:
    cached = _cached("task_board")
    if cached is not None:
        return cached
    tasks: list[TaskItem] = []
    db_path = _state_db_path()
    if db_path:
        try:
            with _connect_state_db(db_path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(threads)")}
                def field(name, fallback="NULL"):
                    return name if name in columns else f"{fallback} AS {name}"
                order_fields = [name for name in ("archived_at", "recency_at", "updated_at", "created_at") if name in columns]
                order_expr = "COALESCE(" + ", ".join(order_fields) + ")" if len(order_fields) > 1 else (order_fields[0] if order_fields else "rowid")
                rows = conn.execute(
                    "SELECT " + ", ".join((
                        field("id", "rowid"), field("title", "''"), field("preview", "''"),
                        field("cwd", "''"), field("archived", "0"), field("created_at"),
                        field("updated_at"), field("recency_at"), field("archived_at"),
                    )) + f" FROM threads ORDER BY {order_expr} DESC LIMIT 300"
                ).fetchall()
                now = datetime.now(timezone.utc)
                for tid, title, preview, cwd, archived, created, updated, recency, archived_at in rows:
                    classification = _classify_thread_task(
                        archived, created, updated, recency, archived_at, now,
                    )
                    if classification is None:
                        continue
                    status, activity_at = classification
                    project = Path(str(cwd).replace("\\\\?\\", "")).name if cwd else ""
                    tasks.append(TaskItem(
                        id=str(tid),
                        title=_clean_task_title(title or preview),
                        status=status,
                        runtime=RuntimeScope.CODEX,
                        updated_at=activity_at,
                        project=project,
                    ))
        except sqlite3.Error:
            pass

    auto_dir = _automations_dir()
    if auto_dir.exists():
        for path in auto_dir.rglob("automation.toml"):
            try:
                content = path.read_text(encoding="utf-8")
                enabled = re.search(r"enabled\s*=\s*true", content, re.IGNORECASE)
                active = re.search(r"status\s*=\s*[\"']ACTIVE[\"']", content, re.IGNORECASE)
                if enabled is None and active is None:
                    continue
                match = re.search(r'name\s*=\s*["\']([^"\']+)', content)
                tasks.append(TaskItem(
                    id=str(path),
                    title=match.group(1) if match else path.parent.name,
                    status="scheduled",
                    runtime=RuntimeScope.CODEX,
                ))
            except (OSError, UnicodeError):
                continue
    return _store("task_board", tasks)


def read_projects() -> list[ProjectStats]:
    cached = _cached("projects")
    if cached is not None:
        return cached
    data = defaultdict(lambda: {
        "name": "", "tokens": 0, "threads": 0, "last": None,
        "breakdown": TokenBreakdown(), "recent": TokenBreakdown(),
        "week": TokenBreakdown(), "month": TokenBreakdown(),
        "models": defaultdict(TokenBreakdown),
        "recent_models": defaultdict(TokenBreakdown),
        "week_models": defaultdict(TokenBreakdown),
        "month_models": defaultdict(TokenBreakdown),
        "priced_tokens": 0,
        "week_priced_tokens": 0,
        "month_priced_tokens": 0,
        "sessions": defaultdict(lambda: {"tokens": 0, "last": None, "models": defaultdict(TokenBreakdown)}),
    })
    seen_paths: set[Path] = set()
    path_projects = _thread_project_map()
    today = get_statistics_timezone().now_date()
    recent_start = today - timedelta(days=6)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def add(target: TokenBreakdown, value: TokenBreakdown):
        target.cached_input += value.cached_input
        target.uncached_input += value.uncached_input
        target.output += value.output

    def priced_value(by_model) -> float:
        return round(sum(
            estimate_model_api_value(tokens, model) or 0.0
            for model, tokens in by_model.items()
        ), 2)

    for path, mtime, timestamp, breakdown, event in _iter_token_deltas():
        directory = _project_name(path, event, path_projects)
        if not directory:
            continue
        key = _normalized_path(directory)
        item = data[key]
        item["name"] = directory.name
        if path not in seen_paths:
            item["threads"] += 1
            seen_paths.add(path)
        if item["last"] is None or mtime > item["last"]:
            item["last"] = mtime
        item["tokens"] += breakdown.total
        model = str(event.get("_codexu_model") or "")
        session = item["sessions"][path]
        session["tokens"] += breakdown.total
        session_time = _event_date(timestamp, mtime)
        if session["last"] is None or session_time > session["last"]:
            session["last"] = session_time
        add(session["models"][model], breakdown)
        day = _event_date(timestamp, mtime).date()
        add(item["breakdown"], breakdown)
        add(item["models"][model], breakdown)
        if estimate_model_api_value(TokenBreakdown(), model) is not None:
            item["priced_tokens"] += breakdown.total
        if recent_start <= day <= today:
            add(item["recent"], breakdown)
            add(item["recent_models"][model], breakdown)
        if week_start <= day <= today:
            add(item["week"], breakdown)
            add(item["week_models"][model], breakdown)
            if estimate_model_api_value(TokenBreakdown(), model) is not None:
                item["week_priced_tokens"] += breakdown.total
        if month_start <= day <= today:
            add(item["month"], breakdown)
            add(item["month_models"][model], breakdown)
            if estimate_model_api_value(TokenBreakdown(), model) is not None:
                item["month_priced_tokens"] += breakdown.total
    def model_usage(by_model):
        result = []
        for model, tokens in by_model.items():
            total = tokens.total
            if not total:
                continue
            value = estimate_model_api_value(tokens, model)
            result.append(ModelUsage(
                name=model or "未知模型",
                token_total=total,
                estimated_value=value or 0.0,
                pricing_coverage_pct=100.0 if value is not None else 0.0,
            ))
        return sorted(result, key=lambda item: item.token_total, reverse=True)

    def session_usage(by_path):
        result = []
        for path, session in by_path.items():
            models = model_usage(session["models"])
            result.append(SessionUsage(
                session_id=path.stem.replace("rollout-", "")[-12:],
                token_total=session["tokens"],
                last_active=session["last"],
                model=models[0].name if models else "未知模型",
            ))
        return sorted(result, key=lambda item: item.last_active or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:100]

    name_counts = defaultdict(int)
    for item in data.values():
        name_counts[item["name"]] += 1
    result = [
        ProjectStats(
            name=(item["name"] if name_counts[item["name"]] == 1 else f"{item['name']} · {Path(key).parent}"),
            token_total=int(item["tokens"]),
            estimated_value=priced_value(item["models"]),
            thread_count=int(item["threads"]),
            last_active=item["last"],
            runtime=RuntimeScope.CODEX,
            last_7d_token_total=item["recent"].total,
            last_7d_estimated_value=priced_value(item["recent_models"]),
            current_week_token_total=item["week"].total,
            current_week_estimated_value=priced_value(item["week_models"]),
            current_week_pricing_coverage_pct=(
                item["week_priced_tokens"] / item["week"].total * 100 if item["week"].total else 0.0
            ),
            current_month_token_total=item["month"].total,
            current_month_estimated_value=priced_value(item["month_models"]),
            current_month_pricing_coverage_pct=(
                item["month_priced_tokens"] / item["month"].total * 100 if item["month"].total else 0.0
            ),
            pricing_coverage_pct=item["priced_tokens"] / item["tokens"] * 100 if item["tokens"] else 0.0,
            source_label="精细统计",
            model_usage=model_usage(item["models"]),
            sessions=session_usage(item["sessions"]),
        )
        for key, item in data.items()
    ]
    result.sort(key=lambda item: item.token_total, reverse=True)
    return _store("projects", result[:20])


def _normalized_path(value: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(value).replace("\\\\?\\", "")))


_DATE_DIRECTORY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PROJECT_MARKERS = (
    ".git", "AGENTS.md", "package.json", "pyproject.toml", "requirements.txt",
    "Cargo.toml", "go.mod", ".openai", ".codex",
)


def _project_directory(value: str | Path) -> Optional[Path]:
    raw = str(value or "").replace("\\\\?\\", "").strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        if not path.is_absolute() or not path.is_dir():
            return None
        resolved = path.resolve()
        if resolved == Path.home().resolve():
            return None
        if _DATE_DIRECTORY.match(resolved.name) or _DATE_DIRECTORY.match(resolved.parent.name):
            return None
        lowered_parts = {part.lower() for part in resolved.parts}
        if ".codex" in lowered_parts or "appdata" in lowered_parts or "temp" in lowered_parts:
            return None
        if any((resolved / marker).exists() for marker in _PROJECT_MARKERS):
            return resolved
        # Creative projects may not have a code manifest. Keep an existing,
        # non-empty directory, but exclude the date-scoped chat workspaces above.
        if any(resolved.iterdir()):
            return resolved
    except (OSError, RuntimeError):
        return None
    return None


def _thread_project_map() -> dict[str, Optional[Path]]:
    db_path = _state_db_path()
    if not db_path:
        return {}
    result = {}
    try:
        with _connect_state_db(db_path) as conn:
            rows = conn.execute(
                "SELECT rollout_path, cwd FROM threads "
                "WHERE rollout_path IS NOT NULL AND cwd IS NOT NULL"
            ).fetchall()
        for rollout_path, cwd in rows:
            directory = _project_directory(cwd)
            result[_normalized_path(rollout_path)] = directory
    except sqlite3.Error:
        return {}
    return result


def _project_name(
    path: Path,
    event: dict,
    path_projects: Optional[dict[str, Optional[str]]] = None,
) -> Optional[Path]:
    """Return only an existing project directory, never a chat/session label."""
    normalized = _normalized_path(path)
    if path_projects is not None and normalized in path_projects:
        return path_projects[normalized]
    candidates = [event.get("cwd"), event.get("directory")]
    payload = event.get("payload")
    if isinstance(payload, dict):
        candidates.extend([payload.get("cwd"), payload.get("directory")])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            directory = _project_directory(value)
            if directory:
                return directory
    return None


def _names_from_event(event: dict, key: str) -> list[str]:
    values = event.get(key)
    if isinstance(values, str):
        return [values]
    if isinstance(values, dict):
        values = [values]
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        if isinstance(value, str):
            result.append(value)
        elif isinstance(value, dict):
            name = value.get("name") or value.get("tool") or value.get("skill")
            if isinstance(name, str):
                result.append(name)
    return result


def _tool_category(name: str) -> str:
    lowered = name.lower()
    if any(token in lowered for token in ("git", "commit", "branch", "diff")):
        return "版本控制"
    if any(token in lowered for token in ("file", "read", "write", "patch", "edit")):
        return "文件操作"
    if any(token in lowered for token in ("terminal", "shell", "exec", "command")):
        return "命令执行"
    if any(token in lowered for token in ("web", "http", "search", "browser")):
        return "网络访问"
    return "其他"


def read_tool_usage() -> list[ToolUsage]:
    cached = _cached("tool_usage")
    if cached is not None:
        return cached
    counts: defaultdict[str, int] = defaultdict(int)
    for _, _, event in _iter_rollout_events():
        payload = event.get("payload")
        if isinstance(payload, dict) and payload.get("type") in ("function_call", "custom_tool_call"):
            name = payload.get("name")
            if isinstance(name, str) and name.strip():
                counts[name.strip()] += 1
            continue
    result = sorted(
        [ToolUsage(
            name=name,
            call_count=count,
            runtime=RuntimeScope.CODEX,
            category=_tool_category(name),
        ) for name, count in counts.items()],
        key=lambda item: item.call_count,
        reverse=True,
    )
    return _store("tool_usage", result)


def read_skill_usage() -> list[SkillUsage]:
    cached = _cached("skill_usage")
    if cached is not None:
        return cached
    counts: defaultdict[str, int] = defaultdict(int)
    skill_paths = (
        re.compile(r"skill://[A-Za-z0-9_./:@+-]+", re.IGNORECASE),
        re.compile(
            r"(?:[A-Za-z]:)?(?:[/\\][A-Za-z0-9_.$@:+~-]+){2,}[/\\]SKILL\.md",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:[A-Za-z0-9_.$@:+~-]+[/\\]){1,8}SKILL\.md",
            re.IGNORECASE,
        ),
    )

    def skill_name(value: str) -> Optional[str]:
        normalized = value.replace("\\", "/").rstrip("/.,;)")
        if normalized.lower().startswith("skill://"):
            parts = [part for part in normalized[8:].split("/") if part]
            candidate = parts[-2] if parts and parts[-1].lower() == "skill.md" else parts[-1]
        else:
            parts = [part for part in normalized.split("/") if part]
            candidate = parts[-2] if len(parts) >= 2 else ""
        if not candidate or candidate.lower() in {"skills", "skill", "$n"} or "$" in candidate:
            return None
        return candidate

    for _, _, event in _iter_rollout_events():
        for key in ("skill", "skills"):
            for name in _names_from_event(event, key):
                counts[name] += 1
        payload = event.get("payload")
        if isinstance(payload, dict):
            for key in ("skill", "skills"):
                for name in _names_from_event(payload, key):
                    counts[name] += 1
            if payload.get("type") in ("function_call", "custom_tool_call"):
                tool_name = str(payload.get("name") or "")
                raw = payload.get("arguments") or payload.get("input") or ""
                if isinstance(raw, (dict, list)):
                    raw = json.dumps(raw, ensure_ascii=False)
                if isinstance(raw, str) and tool_name in {
                    "shell_command", "exec", "read_mcp_resource", "read_mcp_resources",
                }:
                    raw = raw.replace("\\\\", "\\")
                    read_markers = (
                        "get-content", "read_mcp_resource", "skills.read", "cat ",
                        "type ", "more ", "less ", "read_text", ".open(", "rg ",
                    )
                    if tool_name in {"shell_command", "exec"} and not any(
                        marker in raw.lower() for marker in read_markers
                    ):
                        continue
                    # A Skill is counted only when an actual tool invocation addresses
                    # its SKILL.md. Merely listing installed skills is not usage.
                    names = set()
                    for pattern in skill_paths:
                        for match in pattern.finditer(raw):
                            if name := skill_name(match.group(0)):
                                names.add(name)
                    for name in names:
                        counts[name] += 1
    result = sorted(
        [SkillUsage(name=name, use_count=count, runtime=RuntimeScope.CODEX) for name, count in counts.items()],
        key=lambda item: item.use_count,
        reverse=True,
    )
    return _store("skill_usage", result)


def read_codex_snapshot() -> UsageSnapshot:
    _set_quota_status(QUOTA_STATUS_UNAVAILABLE)
    quota = read_quota_from_appserver()
    if quota is None or (
        not any(quota) and get_last_quota_status() == QUOTA_STATUS_UNAVAILABLE
    ):
        session_quota = read_quota_from_session_events()
        if session_quota is not None or get_last_quota_status() != QUOTA_STATUS_UNAVAILABLE:
            quota = session_quota
    quota_status = get_last_quota_status()
    db_tokens = read_token_totals_from_db()
    session_tokens = read_session_tokens()
    daily = read_daily_tokens()
    if daily:
        today = get_statistics_timezone().now_date()
        rolling_start = today - timedelta(days=6)
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        today_tokens = TokenBreakdown()
        rolling_tokens = TokenBreakdown()
        week_tokens = TokenBreakdown()
        month_tokens = TokenBreakdown()
        for item in daily:
            item_date = item.date.date() if hasattr(item.date, "date") else item.date
            if item_date == today:
                today_tokens.cached_input += item.cached_input
                today_tokens.uncached_input += item.uncached_input
                today_tokens.output += item.output
            if rolling_start <= item_date <= today:
                rolling_tokens.cached_input += item.cached_input
                rolling_tokens.uncached_input += item.uncached_input
                rolling_tokens.output += item.output
            if week_start <= item_date <= today:
                week_tokens.cached_input += item.cached_input
                week_tokens.uncached_input += item.uncached_input
                week_tokens.output += item.output
            if month_start <= item_date <= today:
                month_tokens.cached_input += item.cached_input
                month_tokens.uncached_input += item.uncached_input
                month_tokens.output += item.output
        tokens = TokenStats(
            today=today_tokens,
            last_7d=rolling_tokens,
            current_week=week_tokens,
            cumulative=session_tokens,
            current_month=month_tokens,
        )
    else:
        tokens = db_tokens or TokenStats(cumulative=session_tokens)
    priced = read_model_priced_values()
    return UsageSnapshot(
        quota_5h=quota[0] if quota else None,
        quota_7d=quota[1] if quota else None,
        quota_status=quota_status,
        tokens=tokens,
        api_equivalent_value=float(priced["cumulative"]),
        today_api_equivalent_value=float(priced["today"]),
        last_7d_api_equivalent_value=float(priced["rolling_week"]),
        current_week_api_equivalent_value=float(priced["week"]),
        monthly_api_equivalent_value=float(priced["month"]),
        pricing_coverage_pct=float(priced["coverage_pct"]),
        unpriced_token_total=int(priced["unpriced_tokens"]),
        cumulative_index_total=read_thread_index_token_total(),
    )
