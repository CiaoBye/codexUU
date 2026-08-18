from __future__ import annotations

import atexit
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import time
from queue import Empty, Queue
from threading import Lock, Thread
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.data.models import (
    DailyToken,
    ModelUsage,
    ProjectStats,
    QuotaInfo,
    QuotaWindows,
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
_CACHE_LIMIT = 128
_rollout_file_cache: dict[Path, tuple[int, int, datetime, list[dict]]] = {}
_ROLLOUT_FILE_CACHE_LIMIT = 1024
_MAX_ROLLOUT_LINES = 100_000
_MAX_ROLLOUT_LINE_BYTES = 4 * 1024 * 1024
_MAX_ROLLOUT_EVENTS = 250_000
_MAX_ROLLOUT_EVENT_TEXT_BYTES = 16 * 1024
_MAX_ROLLOUT_EVENT_ITEMS = 128
_MAX_APP_SERVER_LINE_BYTES = 4 * 1024 * 1024
_MAX_RUNTIME_THREADS = 300
_MAX_TASK_ITEMS = 300
_MAX_TOKEN_VALUE = 10**15
_last_quota_status = QUOTA_STATUS_UNAVAILABLE
_last_quota_windows = QuotaWindows()
RUNTIME_STATUS_UNAVAILABLE = "unavailable"
RUNTIME_STATUS_STARTING = "starting"
RUNTIME_STATUS_READY = "ready"
RUNTIME_STATUS_TIMEOUT = "timeout"
RUNTIME_STATUS_DISCONNECTED = "disconnected"
RUNTIME_STATUS_EXITED = "exited"
# Spawning the Desktop-managed standalone runtime for every 60-second token
# refresh can make Codex repeatedly recycle that helper process.  Keep a
# successfully verified live quota briefly; session/token aggregation still
# refreshes on every cycle.
_LIVE_QUOTA_TTL_SECONDS = 300
_live_quota_cache: Optional[tuple] = None


def _cached(key: str):
    item = _cache.get(key)
    if item and time.time() - item[0] < _CACHE_TTL:
        return item[1]
    return None


def _store(key: str, value):
    if key not in _cache and len(_cache) >= _CACHE_LIMIT:
        oldest = min(_cache, key=lambda item: _cache[item][0])
        _cache.pop(oldest, None)
    _cache[key] = (time.time(), value)
    return value


def clear_cache():
    """清除聚合快照；保留 rollout 文件级缓存，避免重复解析未变化日志。"""
    global _last_quota_status, _last_quota_windows
    _cache.clear()
    _last_quota_status = QUOTA_STATUS_UNAVAILABLE
    _last_quota_windows = QuotaWindows()


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


def get_last_quota_windows() -> QuotaWindows:
    return _last_quota_windows


def _status_from_rate_limits(
    limits: object,
    quota: tuple[Optional[QuotaInfo], Optional[QuotaInfo]],
    authoritative: Optional[bool] = None,
    extra_quota: Optional[QuotaInfo] = None,
) -> str:
    if authoritative is False:
        return QUOTA_STATUS_UNAVAILABLE
    if any(quota) or extra_quota is not None:
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


_NO_APP_SERVER_RESPONSE = object()


class _CodexAppServerSession:
    """Keep one hidden app-server connection for quota and thread reads."""

    def __init__(self):
        self._lock = Lock()
        self._process = None
        self._executable = ""
        self._messages: Queue[dict] = Queue()
        self._next_request_id = 1
        self._state_lock = Lock()
        self._status = RUNTIME_STATUS_UNAVAILABLE
        self._last_error = ""
        self._status_changed_at = None

    def _set_status(self, status: str, error: str = ""):
        with self._state_lock:
            self._status = status
            self._last_error = str(error or "")[:500]
            self._status_changed_at = datetime.now(timezone.utc)

    def diagnostics(self) -> dict:
        with self._state_lock:
            return {
                "status": self._status,
                "executable": self._executable,
                "last_error": self._last_error,
                "changed_at": self._status_changed_at,
                "alive": self._process is not None and self._process.poll() is None,
            }

    def _read_stdout(self, stream, messages: Queue):
        try:
            for line in stream:
                if len(line) > _MAX_APP_SERVER_LINE_BYTES:
                    continue
                try:
                    message = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(message, dict):
                    messages.put(message)
        finally:
            messages.put({"_codexu_eof": True})

    def _write(self, message: dict) -> bool:
        if self._process is None or self._process.stdin is None:
            return False
        try:
            self._process.stdin.write(json.dumps(message) + "\n")
            self._process.stdin.flush()
            return True
        except (OSError, ValueError):
            return False

    @property
    def is_alive(self) -> bool:
        alive = self._process is not None and self._process.poll() is None
        if not alive and self._process is not None and self._process.poll() is not None:
            self._set_status(RUNTIME_STATUS_EXITED, f"process exited: {self._process.returncode}")
        return alive

    def _wait_for_response(self, request_id: int, timeout: float):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                message = self._messages.get(timeout=0.15)
            except Empty:
                if self._process is None or self._process.poll() is not None:
                    self._set_status(RUNTIME_STATUS_EXITED, "app-server process exited while waiting")
                    return _NO_APP_SERVER_RESPONSE
                continue
            if message.get("_codexu_eof"):
                self._set_status(RUNTIME_STATUS_DISCONNECTED, "app-server stdout closed")
                return _NO_APP_SERVER_RESPONSE
            if message.get("id") != request_id:
                continue
            if "error" in message:
                self._set_status(RUNTIME_STATUS_DISCONNECTED, str(message.get("error")))
                return _NO_APP_SERVER_RESPONSE
            return message.get("result", _NO_APP_SERVER_RESPONSE)
        self._set_status(RUNTIME_STATUS_TIMEOUT, f"response timeout after {timeout:g}s")
        return _NO_APP_SERVER_RESPONSE

    def _stop_locked(self):
        process = self._process
        self._process = None
        self._executable = ""
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except (OSError, ValueError):
            pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    def _start_locked(self, executable: str) -> bool:
        if self._process is not None and self._process.poll() is None and self._executable == executable:
            return True
        self._stop_locked()
        self._set_status(RUNTIME_STATUS_STARTING)
        creation_flags = 0
        if os.name == "nt":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            process = subprocess.Popen(
                [executable, "app-server", "--stdio"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creation_flags,
            )
        except (OSError, subprocess.SubprocessError):
            self._set_status(RUNTIME_STATUS_UNAVAILABLE, "unable to start app-server")
            return False
        if process.stdin is None or process.stdout is None:
            process.kill()
            self._set_status(RUNTIME_STATUS_EXITED, "app-server pipes unavailable")
            return False
        self._process = process
        self._executable = executable
        messages: Queue[dict] = Queue()
        self._messages = messages
        Thread(target=self._read_stdout, args=(process.stdout, messages), daemon=True).start()
        initialize_id = self._next_request_id
        self._next_request_id += 1
        if not self._write({
            "jsonrpc": "2.0",
            "id": initialize_id,
            "method": "initialize",
            "params": {"clientInfo": {"name": "CodexUU", "version": APP_VERSION.lstrip("v")}},
        }):
            self._set_status(RUNTIME_STATUS_DISCONNECTED, "failed to write initialize request")
            self._stop_locked()
            return False
        if self._wait_for_response(initialize_id, 8.0) is _NO_APP_SERVER_RESPONSE:
            self._stop_locked()
            return False
        if not self._write({"jsonrpc": "2.0", "method": "initialized", "params": {}}):
            self._set_status(RUNTIME_STATUS_DISCONNECTED, "failed to write initialized notification")
            self._stop_locked()
            return False
        self._set_status(RUNTIME_STATUS_READY)
        return True

    def request(self, executable: str, method: str, params=None):
        with self._lock:
            if not self._start_locked(executable):
                return None
            request_id = self._next_request_id
            self._next_request_id += 1
            if not self._write({
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }):
                self._set_status(RUNTIME_STATUS_DISCONNECTED, f"failed to write {method} request")
                self._stop_locked()
                return None
            result = self._wait_for_response(request_id, 8.0)
            if result is _NO_APP_SERVER_RESPONSE:
                self._stop_locked()
                return None
            self._set_status(RUNTIME_STATUS_READY)
            return result

    def close(self):
        with self._lock:
            self._stop_locked()


_appserver_session = _CodexAppServerSession()
atexit.register(_appserver_session.close)


def get_appserver_diagnostics() -> dict:
    """Return a bounded, read-only snapshot for the settings diagnostics UI."""
    return _appserver_session.diagnostics()


def _appserver_rate_limits(executable: str) -> Optional[dict]:
    """Read one current rate-limit response over the shared session."""
    result = _appserver_session.request(executable, "account/rateLimits/read", None)
    return result if isinstance(result, dict) else None


def _appserver_thread_list(executable: str) -> Optional[list[dict]]:
    """Read current threads over the same app-server session as quota."""
    result = _appserver_session.request(
        executable,
        "thread/list",
        {"limit": 300, "sortKey": "recency_at", "sortDirection": "desc", "useStateDbOnly": True},
    )
    if not isinstance(result, dict):
        return None
    rows = result.get("data", result.get("threads"))
    if not isinstance(rows, list):
        return None
    # A valid but unexpectedly large response is safer as an empty board than
    # as an unbounded UI/memory allocation or a stale fallback.
    return rows if len(rows) <= _MAX_RUNTIME_THREADS else []


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


def _reset_metadata_from_payload(payload: dict) -> tuple[Optional[int], tuple[datetime, ...]]:
    metadata = payload.get("rateLimitResetCredits", payload.get("rate_limit_reset_credits"))
    if not isinstance(metadata, dict):
        return None, ()
    count = metadata.get("availableCount", metadata.get("available_count"))
    try:
        count = int(count) if count is not None else None
    except (TypeError, ValueError, OverflowError):
        count = None
    if count is not None and count < 0:
        count = None
    credits = metadata.get("credits")
    if not isinstance(credits, list):
        credits = []
    times = []
    for credit in credits:
        if isinstance(credit, dict):
            times.extend(_quota_reset_times(credit))
    return count, tuple(sorted(set(times)))


def read_quota_from_appserver() -> Optional[tuple[Optional[QuotaInfo], Optional[QuotaInfo]]]:
    """Read rolling rate limits when the local Codex CLI is available."""
    global _last_quota_windows, _live_quota_cache
    now = time.monotonic()
    if _live_quota_cache is not None:
        checked_at, quota, status = _live_quota_cache[:3]
        if _appserver_session.is_alive and now - checked_at < _LIVE_QUOTA_TTL_SECONDS:
            _set_quota_status(status)
            _last_quota_windows = (
                _live_quota_cache[3]
                if len(_live_quota_cache) > 3
                else QuotaWindows(five_hour=quota[0], seven_day=quota[1], authoritative=True)
            )
            return quota
        # A dead Runtime must not keep serving its last window during the TTL;
        # the caller needs to attempt a fresh read or fall back to session data.
        _live_quota_cache = None
    for executable in _appserver_executables():
        payload = _appserver_rate_limits(executable)
        if not isinstance(payload, dict):
            continue
        limits = _codex_rate_limits_from_response(payload)
        reset_count, reset_times = _reset_metadata_from_payload(payload)
        windows = _displayable_quota_windows(_normalize_rate_limits(limits, reset_count, reset_times))
        quota = windows.pair
        status = _status_from_rate_limits(limits, quota, windows.authoritative, windows.monthly)
        _set_quota_status(status)
        _last_quota_windows = windows
        _live_quota_cache = (now, quota, status, windows)
        return quota
    _last_quota_windows = QuotaWindows()
    _set_quota_status(QUOTA_STATUS_UNAVAILABLE)
    return None


def _quota_reset_times(item: dict) -> tuple[datetime, ...]:
    values = item.get(
        "reset_times",
        item.get("resetTimes", item.get("resetsAt", item.get("expiresAt", item.get("expires_at")))),
    )
    if values is None:
        values = item.get("resets_at", item.get("resetAt"))
    if not isinstance(values, (list, tuple)):
        values = [values] if values is not None else []
    return tuple(reset for reset in (_parse_reset(value) for value in values) if reset is not None)


def _quota_from_item(
    item: object,
    reset_count: Optional[int] = None,
    reset_times: tuple[datetime, ...] = (),
) -> tuple[Optional[int], Optional[QuotaInfo], bool]:
    if item is None:
        return None, None, False
    if not isinstance(item, dict):
        return None, None, True
    raw_window = item.get("window_minutes", item.get("windowDurationMins"))
    try:
        window = int(raw_window) if raw_window is not None else None
    except (TypeError, ValueError, OverflowError):
        return None, None, True
    used = item.get("used_percent", item.get("usedPercent", item.get("used")))
    maximum = item.get("max", item.get("limit"))
    try:
        if maximum not in (None, 0):
            used_pct = float(used or 0) / float(maximum) * 100
        elif used is not None:
            used_pct = float(used)
        else:
            return window, None, True
    except (TypeError, ValueError, OverflowError, ZeroDivisionError):
        return window, None, True
    if not 0 <= used_pct <= 100:
        return window, None, True
    item_reset_count = item.get("reset_count", item.get("resetCount"))
    if item_reset_count is not None:
        try:
            item_reset_count = int(item_reset_count)
        except (TypeError, ValueError, OverflowError):
            return window, None, True
        if item_reset_count < 0:
            return window, None, True
    item_reset_times = _quota_reset_times(item) or reset_times
    return window, QuotaInfo(
        used_pct=used_pct,
        remaining_pct=100.0 - used_pct,
        reset_time=item_reset_times[0] if item_reset_times else None,
        window_minutes=window,
        reset_count=item_reset_count if item_reset_count is not None else reset_count,
        reset_times=item_reset_times,
    ), False


def _normalize_rate_limits(
    limits: object,
    reset_count: Optional[int] = None,
    reset_times: tuple[datetime, ...] = (),
) -> QuotaWindows:
    if not isinstance(limits, dict):
        return QuotaWindows(malformed_count=1)
    known_keys = ("5h", "7d", "monthly", "primary", "secondary")
    keys = [key for key in known_keys if key in limits]
    # New Runtime versions may add another named slot.  Only treat an extra
    # dictionary as a quota candidate when it carries an explicit duration;
    # unrelated scalar metadata remains ignored.
    for key, item in limits.items():
        if key in known_keys or not isinstance(item, dict):
            continue
        if "window_minutes" in item or "windowDurationMins" in item:
            keys.append(key)
    candidates: dict[str, list[QuotaInfo]] = {"five_hour": [], "seven_day": [], "monthly": []}
    unclassified = 0
    malformed = 0
    for key in keys:
        if limits.get(key) is None:
            continue
        window, quota, invalid = _quota_from_item(limits.get(key), reset_count, reset_times)
        if invalid:
            malformed += 1
            continue
        if window == 300:
            candidates["five_hour"].append(quota)
        elif window == 10080:
            candidates["seven_day"].append(quota)
        elif window is not None and 28 * 24 * 60 <= window <= 31 * 24 * 60:
            candidates["monthly"].append(quota)
        else:
            unclassified += 1
    five_hour = candidates["five_hour"][0] if len(candidates["five_hour"]) == 1 else None
    seven_day = candidates["seven_day"][0] if len(candidates["seven_day"]) == 1 else None
    monthly = candidates["monthly"][0] if len(candidates["monthly"]) == 1 else None
    duplicate_count = sum(max(0, len(items) - 1) for items in candidates.values())
    has_window_fields = bool(keys)
    authoritative = (
        has_window_fields
        and not malformed
        and not unclassified
        and duplicate_count == 0
    )
    return QuotaWindows(
        five_hour=five_hour,
        seven_day=seven_day,
        monthly=monthly,
        unclassified_count=unclassified,
        malformed_count=malformed,
        duplicate_count=duplicate_count,
        authoritative=authoritative,
    )


def _quota_pair_from_rate_limits(limits: dict) -> tuple[Optional[QuotaInfo], Optional[QuotaInfo]]:
    return _normalize_rate_limits(limits).pair


def _displayable_quota_windows(windows: QuotaWindows) -> QuotaWindows:
    if windows.authoritative:
        return windows
    return QuotaWindows(
        unclassified_count=windows.unclassified_count,
        malformed_count=windows.malformed_count,
        duplicate_count=windows.duplicate_count,
        authoritative=False,
    )


def read_quota_from_session_events() -> Optional[tuple[Optional[QuotaInfo], Optional[QuotaInfo]]]:
    """Read the newest persisted Codex rate-limit snapshot without a full history scan."""
    global _last_quota_windows
    cached = _cached("quota_session_events")
    if cached is not None:
        _set_quota_status(_cached("quota_session_status") or QUOTA_STATUS_UNAVAILABLE)
        _last_quota_windows = _cached("quota_session_windows") or QuotaWindows(
            five_hour=cached[0], seven_day=cached[1], authoritative=True,
        )
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
            reset_count, reset_times = _reset_metadata_from_payload(payload)
            windows = _displayable_quota_windows(_normalize_rate_limits(limits, reset_count, reset_times))
            result = windows.pair
            status = _status_from_rate_limits(limits, result, windows.authoritative, windows.monthly)
            # A newest event with explicit empty windows is authoritative: do
            # not resurrect an older quota snapshot after a reset or account
            # state change.  Codex uses this empty shape after exhaustion, so
            # preserve the status even though there is no honest window to draw.
            _set_quota_status(status)
            _last_quota_windows = windows
            _store("quota_session_status", status)
            _store("quota_session_windows", windows)
            return _store("quota_session_events", result)
    _set_quota_status(QUOTA_STATUS_UNAVAILABLE)
    _last_quota_windows = QuotaWindows()
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


_TOKEN_USAGE_FIELDS = (
    "input_tokens", "input", "cached_input_tokens", "cached_input",
    "uncached_input", "output_tokens", "output", "reasoning_output_tokens",
    "reasoning_output", "reasoning", "total_tokens", "total",
)
_EVENT_CONTEXT_FIELDS = (
    "id", "session_id", "parent_thread_id", "parentThreadId", "cwd", "directory",
    "model", "effort", "reasoning_effort", "turn_id", "name",
)
_RATE_LIMIT_FIELDS = (
    "rate_limits", "rateLimitResetCredits", "rate_limit_reset_credits",
)


def _compact_event_text(value) -> str:
    if isinstance(value, str):
        return value[:_MAX_ROLLOUT_EVENT_TEXT_BYTES]
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = str(value)
    return encoded[:_MAX_ROLLOUT_EVENT_TEXT_BYTES]


def _compact_event_value(value, depth: int = 0):
    """Copy a small metadata value while dropping unbounded transcript data."""
    if depth > 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_ROLLOUT_EVENT_TEXT_BYTES]
    if isinstance(value, dict):
        return {
            str(key): _compact_event_value(item, depth + 1)
            for key, item in list(value.items())[:_MAX_ROLLOUT_EVENT_ITEMS]
        }
    if isinstance(value, list):
        return [
            _compact_event_value(item, depth + 1)
            for item in value[:_MAX_ROLLOUT_EVENT_ITEMS]
        ]
    return str(value)[:_MAX_ROLLOUT_EVENT_TEXT_BYTES]


def _compact_token_usage(value):
    if not isinstance(value, dict):
        return None
    return {
        key: value[key]
        for key in _TOKEN_USAGE_FIELDS
        if key in value and isinstance(value[key], (bool, int, float, str))
    }


def _compact_context(value):
    if not isinstance(value, dict):
        return None
    result = {
        key: _compact_event_value(value[key])
        for key in _EVENT_CONTEXT_FIELDS
        if key in value
    }
    collaboration = value.get("collaboration_mode")
    if isinstance(collaboration, dict):
        settings = collaboration.get("settings")
        if isinstance(settings, dict) and "reasoning_effort" in settings:
            result["collaboration_mode"] = {
                "settings": {"reasoning_effort": _compact_event_value(settings["reasoning_effort"])}
            }
    return result


def _compact_rollout_event(event: dict) -> dict:
    """Keep only fields consumed by the dashboard's aggregators.

    Rollout lines can contain hundreds of megabytes of prompt/tool content.
    The dashboard needs metadata and token counters, not transcript bodies.
    """
    compact = {
        key: _compact_event_value(event[key])
        for key in (
            "timestamp", "created_at", "type", "session_id", "cwd", "directory",
            "model", "effort", "reasoning_effort", "turn_id", "skill", "skills",
        )
        if key in event
    }
    token_count = _compact_token_usage(event.get("token_count"))
    if token_count:
        compact["token_count"] = token_count

    payload = event.get("payload")
    if not isinstance(payload, dict):
        return compact

    compact_payload = {
        key: _compact_event_value(payload[key])
        for key in _EVENT_CONTEXT_FIELDS
        if key in payload
    }
    if "type" in payload:
        compact_payload["type"] = _compact_event_value(payload["type"])
    for key in ("skill", "skills"):
        if key in payload:
            compact_payload[key] = _compact_event_value(payload[key])
    for key in _RATE_LIMIT_FIELDS:
        if key in payload:
            compact_payload[key] = _compact_event_value(payload[key])

    payload_type = payload.get("type")
    if payload_type == "token_count":
        info = payload.get("info")
        if isinstance(info, dict):
            compact_info = {}
            for key in ("total_token_usage", "last_token_usage"):
                usage = _compact_token_usage(info.get(key))
                if usage:
                    compact_info[key] = usage
            if compact_info:
                compact_payload["info"] = compact_info
    elif payload_type in ("function_call", "custom_tool_call"):
        for key in ("arguments", "input"):
            if key in payload:
                compact_payload[key] = _compact_event_text(payload[key])

    thread_settings = payload.get("thread_settings")
    if isinstance(thread_settings, dict):
        compact_payload["thread_settings"] = _compact_context(thread_settings)
    if compact_payload:
        compact["payload"] = compact_payload
    return compact


def _read_rollout_file_events(path: Path, stat: os.stat_result, mtime: datetime) -> list[dict]:
    cached_file = _rollout_file_cache.get(path)
    if cached_file and cached_file[0] == stat.st_mtime_ns and cached_file[1] == stat.st_size:
        return cached_file[3]
    events: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, line in enumerate(handle, 1):
                if line_number > _MAX_ROLLOUT_LINES or len(line) > _MAX_ROLLOUT_LINE_BYTES:
                    _rollout_file_cache.pop(path, None)
                    return []
                event = parse_jsonl_line(line)
                if event:
                    events.append(_compact_rollout_event(event))
    except (OSError, UnicodeError):
        _rollout_file_cache.pop(path, None)
        return []
    _rollout_file_cache[path] = (stat.st_mtime_ns, stat.st_size, mtime, events)
    return events


def _safe_token_int(value) -> Optional[int]:
    if value is None:
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if number < 0 or number > _MAX_TOKEN_VALUE:
        return None
    return number


def _token_sample_values(sample: object) -> tuple[Optional[int], ...]:
    if not isinstance(sample, dict):
        return (None, None, None, None, None)
    values = []
    for key in (
        ("input_tokens", "input"),
        ("cached_input_tokens", "cached_input"),
        ("output_tokens", "output"),
        ("reasoning_output_tokens", "reasoning_output", "reasoning"),
        ("total_tokens", "total"),
    ):
        raw = next((sample[name] for name in key if name in sample), None)
        values.append(_safe_token_int(raw) if raw is not None else None)
    return tuple(values)


def _token_event_fingerprint(event: dict) -> Optional[str]:
    """Hash only bounded token counters; never retain transcript content."""
    if not isinstance(event, dict):
        return None
    payload = event.get("payload")
    total = None
    last = None
    if event.get("type") == "event_msg" and isinstance(payload, dict) and payload.get("type") == "token_count":
        info = payload.get("info", {})
        if isinstance(info, dict):
            total = info.get("total_token_usage")
            last = info.get("last_token_usage")
            if total is None and last is None:
                last = info
    else:
        last = event.get("token_count")
    if total is None and last is None:
        return None
    encoded = json.dumps(
        (_token_sample_values(total), _token_sample_values(last)),
        separators=(",", ":"),
    ).encode("ascii", errors="replace")
    return hashlib.blake2b(encoded, digest_size=16).hexdigest()


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

    cached = _safe_token_int(usage.get("cached_input_tokens", usage.get("cached_input", 0)))
    input_tokens = _safe_token_int(usage.get("input_tokens", usage.get("input", 0)))
    if cached is None or input_tokens is None:
        return None
    uncached = usage.get("uncached_input")
    if uncached is None:
        uncached = max(0, input_tokens - cached)
    else:
        uncached = _safe_token_int(uncached)
    output = _safe_token_int(usage.get("output_tokens", usage.get("output", 0)))
    if uncached is None or output is None:
        return None
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


def _session_link_from_events(path: Path, events: list[dict]) -> tuple[str, str]:
    session_id = ""
    parent_id = ""
    for event in events:
        if not isinstance(event, dict) or event.get("type") != "session_meta":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        session_id = str(payload.get("id") or payload.get("session_id") or event.get("session_id") or "").strip()
        parent_id = str(payload.get("parent_thread_id") or payload.get("parentThreadId") or "").strip()
        if session_id or parent_id:
            break
    if not session_id and isinstance(path, Path):
        match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,})$", path.stem, re.IGNORECASE)
        session_id = match.group(1).lower() if match else ""
    return session_id, parent_id


def _inherited_prefix_length(child: list[str], parent: list[str]) -> int:
    index = 0
    upper_bound = min(len(child), len(parent))
    while index < upper_bound and child[index] and child[index] == parent[index]:
        index += 1
    return index


def _iter_token_deltas(days: Optional[int] = None) -> Iterator[tuple[Path, datetime, str, TokenBreakdown, dict]]:
    cache_key = f"token_deltas:{days if days is not None else 'all'}"
    cached = _cached(cache_key)
    if cached is not None:
        yield from cached
        return
    previous: dict[Path, TokenBreakdown] = {}
    records: list[tuple[Path, datetime, str, TokenBreakdown, dict]] = []
    grouped: dict[Path, tuple[datetime, list[dict]]] = {}
    for path, mtime, event in _iter_rollout_events(days=days):
        if path not in grouped:
            grouped[path] = (mtime, [])
        grouped[path][1].append(event)

    token_entries: dict[Path, list[tuple[str, TokenBreakdown, bool, dict, str, str, str, str]]] = {}
    session_paths: dict[str, Path] = {}
    parent_by_path: dict[Path, str] = {}
    for path, (mtime, events) in grouped.items():
        session_id, parent_id = _session_link_from_events(path, events)
        if session_id:
            session_paths[session_id] = path
        parent_by_path[path] = parent_id
        active_model = active_effort = active_turn = ""
        entries = []
        for event in events:
            model, effort, turn_id = _model_context_from_event(event)
            if model:
                active_model = model
            if effort:
                active_effort = effort
            if turn_id:
                active_turn = turn_id
            parsed = _read_token_event(event)
            if parsed:
                timestamp, current, cumulative = parsed
                entries.append((timestamp, current, cumulative, event, active_model, active_effort, active_turn, _token_event_fingerprint(event) or ""))
        token_entries[path] = entries

    for path, entries in token_entries.items():
        parent_path = session_paths.get(parent_by_path.get(path, ""))
        inherited = 0
        if parent_path is not None:
            inherited = _inherited_prefix_length(
                [entry[7] for entry in entries],
                [entry[7] for entry in token_entries.get(parent_path, ())],
            )
            if inherited and entries[inherited - 1][2]:
                previous[path] = entries[inherited - 1][1]
            entries = entries[inherited:]
        for timestamp, current, cumulative, event, model, effort, turn_id, _fingerprint in entries:
            delta = _delta_breakdown(previous.get(path), current) if cumulative else current
            if cumulative:
                previous[path] = current
            if delta.total > 0:
                event["_codexu_model"] = model
                event["_codexu_effort"] = effort
                event["_codexu_turn_id"] = turn_id
                records.append((path, grouped[path][0], timestamp, delta, event))
                if len(records) > _MAX_ROLLOUT_EVENTS:
                    return
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
                if len(records) > _MAX_ROLLOUT_EVENTS:
                    return _store(cache_key, [])
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
    # Newer thread records carry the authoritative archive timestamp.  Older
    # SQLite layouts may only expose the boolean and updated timestamp.
    if archived_time is not None:
        return "completed", archived_time
    if bool(archived):
        return ("completed", updated) if updated else None
    today = statistics.date_for(now)
    candidates = [value for value in (created, updated, recency) if value is not None]
    if not candidates or not any(statistics.date_for(value) == today for value in candidates):
        return None
    activity = recency or updated or created
    age = now.astimezone(timezone.utc) - activity.astimezone(timezone.utc)
    return ("running" if age <= timedelta(hours=2) else "pending"), activity


def _thread_field(row: dict, *names, default=None):
    for name in names:
        if name in row:
            return row[name]
    return default


def _tasks_from_runtime_rows(rows: list[dict], now: datetime) -> list[TaskItem]:
    tasks: list[TaskItem] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        classification = _classify_thread_task(
            _thread_field(row, "archived", default=False),
            _thread_field(row, "createdAt", "created_at"),
            _thread_field(row, "updatedAt", "updated_at"),
            _thread_field(row, "recencyAt", "recency_at"),
            _thread_field(row, "archivedAt", "archived_at"),
            now,
        )
        if classification is None:
            continue
        status, activity_at = classification
        cwd = _thread_field(row, "cwd", "workingDirectory", "working_directory", default="")
        title = _thread_field(row, "title", "name", default="")
        preview = _thread_field(row, "preview", "firstUserMessage", default="")
        tasks.append(TaskItem(
            id=str(_thread_field(row, "id", "threadId", default="")),
            title=_clean_task_title(title or preview),
            status=status,
            runtime=RuntimeScope.CODEX,
            updated_at=activity_at,
            project=Path(str(cwd).replace("\\\\?\\", "")).name if cwd else "",
        ))
    return tasks


def read_task_board() -> list[TaskItem]:
    cached = _cached("task_board")
    if cached is not None:
        return cached
    tasks: list[TaskItem] = []
    runtime_rows = None
    if _appserver_session.is_alive:
        for executable in _appserver_executables():
            runtime_rows = _appserver_thread_list(executable)
            if runtime_rows is not None:
                break
    if runtime_rows is not None:
        tasks.extend(_tasks_from_runtime_rows(runtime_rows, datetime.now(timezone.utc)))
    else:
        db_path = _state_db_path()
    if runtime_rows is None and db_path:
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
    return _store("task_board", tasks[:_MAX_TASK_ITEMS])


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
    # A tuple, including (None, None), means Runtime answered.  Its empty or
    # malformed result is authoritative for this refresh and must not revive
    # an older session snapshot.  Only a missing Runtime response may fall
    # back to persisted session events.
    if quota is None:
        session_quota = read_quota_from_session_events()
        if session_quota is not None or get_last_quota_status() != QUOTA_STATUS_UNAVAILABLE:
            quota = session_quota
    quota_status = get_last_quota_status()
    quota_windows = get_last_quota_windows()
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
        quota_month=quota_windows.monthly,
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
