from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlsplit

import requests

from app.data.models import (
    DailyToken,
    ProviderBalance,
    ProviderUsageSnapshot,
    TokenBreakdown,
    TokenStats,
    PROVIDER_STATUS_AVAILABLE,
    PROVIDER_STATUS_DEGRADED,
    PROVIDER_STATUS_UNAVAILABLE,
)
from app.utils.statistics_timezone import get_statistics_timezone


_CACHE_TTL_SECONDS = 30
_MAX_PROXY_LOG_ROWS = 100_000
_MAX_USAGE_SCRIPT_BYTES = 256 * 1024
_cache: Optional[tuple[float, Path, ProviderUsageSnapshot]] = None


def _ccswitch_root(root: Optional[Path] = None) -> Path:
    return Path(root) if root is not None else Path.home() / ".cc-switch"


def clear_cache() -> None:
    global _cache
    _cache = None


def _safe_int(value, default: int = 0) -> int:
    try:
        result = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if result >= 0 else default


def _safe_float(value) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result == result else None


def _json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _connect(root: Path) -> sqlite3.Connection:
    path = root / "cc-switch.db"
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=1)
    connection.execute("PRAGMA query_only = ON")
    return connection


def _provider_row(connection: sqlite3.Connection, root: Path) -> Optional[dict]:
    settings = _json_file(root / "settings.json")
    provider_id = settings.get("currentProviderCodex")
    columns = (
        "id, app_type, name, settings_config, meta, provider_type, "
        "is_current"
    )
    row = None
    if provider_id:
        row = connection.execute(
            f"SELECT {columns} FROM providers WHERE id = ? LIMIT 1", (str(provider_id),)
        ).fetchone()
    if row is None:
        row = connection.execute(
            f"SELECT {columns} FROM providers "
            "WHERE app_type = 'codex' AND is_current = 1 LIMIT 1"
        ).fetchone()
    if row is None and provider_id:
        row = connection.execute(
            f"SELECT {columns} FROM providers WHERE app_type = 'codex' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return dict(zip(columns.split(", "), row))


def _provider_config(raw: object) -> dict:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}


def _base_url(config: dict) -> str:
    raw = config.get("config")
    if not isinstance(raw, str):
        return ""
    match = re.search(r"https?://[^\s,;\"']+", raw)
    return match.group(0).rstrip("/") if match else ""


def _api_key(config: dict) -> str:
    auth = config.get("auth")
    if not isinstance(auth, dict):
        return ""
    for key in ("OPENAI_API_KEY", "API_KEY", "apiKey", "token"):
        value = auth.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _usage_script(meta: dict) -> dict:
    script = meta.get("usage_script")
    if not isinstance(script, dict) or not script.get("enabled"):
        return {}
    code = str(script.get("code") or "")
    if len(code.encode("utf-8")) > _MAX_USAGE_SCRIPT_BYTES:
        return {}
    return {
        "code": code,
        "timeout": max(2, min(15, _safe_int(script.get("timeout"), 10))),
        "interval": max(0, _safe_int(script.get("autoQueryInterval"), 0)),
    }


def _usage_request(script: dict, base_url: str, api_key: str) -> Optional[tuple[str, str, dict]]:
    code = script.get("code", "")
    url_match = re.search(r"\burl\s*:\s*['\"]([^'\"]+)", code)
    if not url_match:
        return None
    method_match = re.search(r"\bmethod\s*:\s*['\"]([^'\"]+)", code, re.IGNORECASE)
    method = (method_match.group(1) if method_match else "GET").upper()
    if method not in {"GET", "POST"}:
        return None
    template = url_match.group(1)
    if "{{baseUrl}}" in template:
        url = template.replace("{{baseUrl}}", base_url.rstrip("/"))
    elif template.startswith("/"):
        url = urljoin(base_url.rstrip("/") + "/", template.lstrip("/"))
    else:
        url = template
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    headers = {"Accept": "application/json"}
    code_lower = code.lower()
    if api_key and "authorization" in code_lower and "bearer {{apikey}}" in code_lower:
        headers["Authorization"] = f"Bearer {api_key}"
    elif api_key and "x-api-key" in code_lower and "{{apikey}}" in code_lower:
        headers["X-API-Key"] = api_key
    elif api_key and "api-key" in code_lower and "{{apikey}}" in code_lower:
        headers["api-key"] = api_key
    return method, url, headers


def _value_at(payload: object, path: tuple[str, ...]):
    value = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _first_value(payload: object, paths: tuple[tuple[str, ...], ...]):
    for path in paths:
        value = _value_at(payload, path)
        if value is not None:
            return value
    return None


def _extract_balance(payload: object) -> Optional[ProviderBalance]:
    if not isinstance(payload, dict):
        return None
    quota = _first_value(payload, (("quota",), ("data", "quota")))
    if not isinstance(quota, dict):
        quota = {}
    remaining = _safe_float(_first_value(payload, (
        ("remaining",), ("quota", "remaining"), ("balance",),
        ("data", "remaining"), ("data", "balance"), ("data", "quota", "remaining"),
    )))
    total = _safe_float(_first_value(payload, (
        ("total",), ("quota", "total"), ("data", "total"), ("data", "quota", "total"),
    )))
    used = _safe_float(_first_value(payload, (
        ("used",), ("usage",), ("quota", "used"), ("data", "used"),
        ("data", "quota", "used"),
    )))
    if remaining is None and total is not None and used is not None:
        remaining = max(0.0, total - used)
    unit = _first_value(payload, (("unit",), ("quota", "unit"), ("data", "unit")))
    plan = _first_value(payload, (("planName",), ("plan_name",), ("plan",), ("data", "planName")))
    is_valid = _first_value(payload, (("isValid",), ("is_active",), ("data", "isValid")))
    invalid_message = _first_value(payload, (("invalidMessage",), ("error",), ("message",)))
    if remaining is None and is_valid is None and total is None and used is None:
        return None
    return ProviderBalance(
        remaining=remaining,
        unit=str(unit or "USD"),
        total=total,
        used=used,
        plan_name=str(plan or ""),
        is_valid=bool(is_valid) if is_valid is not None else None,
        invalid_message=str(invalid_message or ""),
    )


def _fetch_balance(config: dict, meta: dict) -> tuple[Optional[ProviderBalance], str]:
    script = _usage_script(meta)
    if not script:
        return None, "CCS 未启用供应商用量查询脚本"
    base_url = _base_url(config)
    api_key = _api_key(config)
    request_spec = _usage_request(script, base_url, api_key)
    if request_spec is None:
        return None, "CCS 用量查询脚本缺少可识别的 HTTP 请求"
    method, url, headers = request_spec
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=script["timeout"],
        )
        if not 200 <= response.status_code < 300:
            return None, f"供应商用量接口 HTTP {response.status_code}"
        payload = response.json()
    except (requests.RequestException, ValueError, TypeError) as error:
        return None, f"供应商用量接口失败：{type(error).__name__}"
    balance = _extract_balance(payload)
    if balance is None:
        return None, "供应商响应未返回可识别的余额字段"
    return replace(balance, checked_at=datetime.now(timezone.utc)), ""


def _epoch_seconds(value) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number // 1000 if number > 10**12 else number


def _day_from_epoch(value) -> Optional[date]:
    timestamp = _epoch_seconds(value)
    if timestamp is None:
        return None
    try:
        return get_statistics_timezone().date_for(datetime.fromtimestamp(timestamp, timezone.utc))
    except (OverflowError, OSError, ValueError):
        return None


def _day_from_text(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _empty_snapshot(detail: str, provider_id: str = "", provider_name: str = "") -> ProviderUsageSnapshot:
    return ProviderUsageSnapshot(
        provider_id=provider_id,
        provider_name=provider_name,
        status=PROVIDER_STATUS_UNAVAILABLE,
        status_detail=detail,
    )


def _aggregate_usage(connection: sqlite3.Connection, provider_id: str, cutoff: date) -> ProviderUsageSnapshot:
    daily: dict[date, dict[str, object]] = defaultdict(lambda: {
        "tokens": TokenBreakdown(), "cost": 0.0, "requests": 0, "success": 0,
    })
    direct_rows = connection.execute(
        """SELECT created_at, model, input_tokens, output_tokens, cache_read_tokens,
                  total_cost_usd, status_code
           FROM proxy_request_logs
           WHERE provider_id = ? AND app_type = 'codex'
             AND created_at >= ?
           ORDER BY created_at ASC
           LIMIT ?""",
        (provider_id, int(datetime.combine(cutoff, datetime.min.time(), tzinfo=timezone.utc).timestamp()), _MAX_PROXY_LOG_ROWS + 1),
    ).fetchall()
    if len(direct_rows) > _MAX_PROXY_LOG_ROWS:
        raise ValueError("CCS proxy_request_logs 超过单轮读取上限")

    direct_days: set[date] = set()
    last_request = None

    def add(day: Optional[date], input_tokens, output_tokens, cached_tokens, cost, requests_count, success_count):
        if day is None or day < cutoff:
            return
        target = daily[day]
        tokens = target["tokens"]
        cached = min(_safe_int(input_tokens), _safe_int(cached_tokens))
        tokens.cached_input += cached
        tokens.uncached_input += max(0, _safe_int(input_tokens) - cached)
        tokens.output += _safe_int(output_tokens)
        target["cost"] = float(target["cost"]) + (_safe_float(cost) or 0.0)
        target["requests"] = int(target["requests"]) + _safe_int(requests_count)
        target["success"] = int(target["success"]) + _safe_int(success_count)

    for created_at, _model, input_tokens, output_tokens, cached_tokens, cost, status_code in direct_rows:
        day = _day_from_epoch(created_at)
        if day is None:
            continue
        direct_days.add(day)
        add(day, input_tokens, output_tokens, cached_tokens, cost, 1, int(200 <= _safe_int(status_code) < 300))
        timestamp = _epoch_seconds(created_at)
        if timestamp is not None:
            current = datetime.fromtimestamp(timestamp, timezone.utc)
            if last_request is None or current > last_request:
                last_request = current

    oldest_direct_day = min(direct_days) if direct_days else cutoff
    rollup_rows = connection.execute(
        """SELECT date, input_tokens, output_tokens, cache_read_tokens,
                  total_cost_usd, request_count, success_count
           FROM usage_daily_rollups
           WHERE provider_id = ? AND app_type = 'codex'
             AND date >= ? AND date < ?
           ORDER BY date ASC""",
        (provider_id, cutoff.isoformat(), oldest_direct_day.isoformat()),
    ).fetchall()
    for day_text, input_tokens, output_tokens, cached_tokens, cost, request_count, success_count in rollup_rows:
        add(_day_from_text(day_text), input_tokens, output_tokens, cached_tokens, cost, request_count, success_count)

    timezone_info = get_statistics_timezone().tzinfo()
    daily_tokens = [
        DailyToken(
            date=datetime.combine(day, datetime.min.time(), tzinfo=timezone_info),
            total=data["tokens"].total,
            cached_input=data["tokens"].cached_input,
            uncached_input=data["tokens"].uncached_input,
            output=data["tokens"].output,
        )
        for day, data in sorted(daily.items(), reverse=True)
    ]
    today = get_statistics_timezone().now_date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    def breakdown(start: date, end: Optional[date] = None) -> TokenBreakdown:
        result = TokenBreakdown()
        for day, data in daily.items():
            if day >= start and (end is None or day <= end):
                source = data["tokens"]
                result.cached_input += source.cached_input
                result.uncached_input += source.uncached_input
                result.output += source.output
        return result

    cumulative = breakdown(cutoff)
    stats = TokenStats(
        today=breakdown(today, today),
        last_7d=breakdown(today - timedelta(days=6), today),
        current_week=breakdown(week_start, today),
        current_month=breakdown(month_start, today),
        cumulative=cumulative,
    )

    def cost(start: date, end: Optional[date] = None) -> float:
        return round(sum(
            float(data["cost"])
            for day, data in daily.items()
            if day >= start and (end is None or day <= end)
        ), 4)

    requests_count = sum(int(data["requests"]) for data in daily.values())
    success_count = sum(int(data["success"]) for data in daily.values())
    if last_request is None and daily_tokens:
        last_request = daily_tokens[0].date.astimezone(timezone.utc)
    return ProviderUsageSnapshot(
        tokens=stats,
        daily_tokens=daily_tokens,
        request_count=requests_count,
        success_count=success_count,
        failure_count=max(0, requests_count - success_count),
        total_cost_usd=cost(cutoff),
        today_cost_usd=cost(today, today),
        current_week_cost_usd=cost(week_start, today),
        current_month_cost_usd=cost(month_start, today),
        last_request_at=last_request,
        status=PROVIDER_STATUS_AVAILABLE if requests_count else PROVIDER_STATUS_UNAVAILABLE,
        status_detail="" if requests_count else "CCS 当前供应商暂无 Codex 请求记录",
        data_source="CC Switch proxy_request_logs + usage_daily_rollups",
    )


def read_ccswitch_snapshot(root: Optional[Path] = None, fetch_balance: bool = True) -> ProviderUsageSnapshot:
    global _cache
    root_path = _ccswitch_root(root)
    if root is None and _cache and time.monotonic() - _cache[0] < _CACHE_TTL_SECONDS and _cache[1] == root_path:
        return _cache[2]
    if not (root_path / "cc-switch.db").exists():
        return _empty_snapshot("未找到 CCS 本机数据库")
    try:
        connection = _connect(root_path)
    except (OSError, sqlite3.Error) as error:
        return _empty_snapshot(f"无法读取 CCS 数据库：{type(error).__name__}")
    provider: Optional[dict] = None
    try:
        provider = _provider_row(connection, root_path)
        if not provider:
            return _empty_snapshot("CCS 未配置当前 Codex 供应商")
        provider_id = str(provider.get("id") or "")
        provider_name = str(provider.get("name") or provider_id)
        cutoff = get_statistics_timezone().now_date() - timedelta(days=180)
        snapshot = _aggregate_usage(connection, provider_id, cutoff)
        snapshot = replace(
            snapshot,
            provider_id=provider_id,
            provider_name=provider_name,
            app_type=str(provider.get("app_type") or "codex"),
            base_url_host=urlsplit(_base_url(_provider_config(provider.get("settings_config")))).hostname or "",
            plan_name="",
        )
        config = _provider_config(provider.get("settings_config"))
        meta = _provider_config(provider.get("meta"))
        script = _usage_script(meta)
        if fetch_balance and script:
            balance, detail = _fetch_balance(config, meta)
            snapshot = replace(snapshot, balance=balance)
            if balance is not None:
                snapshot = replace(snapshot, plan_name=balance.plan_name or snapshot.plan_name)
            elif detail:
                snapshot = replace(
                    snapshot,
                    status=PROVIDER_STATUS_DEGRADED if snapshot.request_count else PROVIDER_STATUS_UNAVAILABLE,
                    status_detail=detail,
                )
        elif script:
            snapshot = replace(snapshot, quota_query_enabled=True)
        else:
            snapshot = replace(snapshot, quota_query_enabled=False)
        if snapshot.balance is not None:
            snapshot = replace(snapshot, quota_query_enabled=True)
        if root is None:
            _cache = (time.monotonic(), root_path, snapshot)
        return snapshot
    except (sqlite3.Error, OSError, ValueError, TypeError) as error:
        return _empty_snapshot(
            f"读取 CCS 用量失败：{type(error).__name__}",
            str(provider.get("id") or "") if isinstance(provider, dict) else "",
            str(provider.get("name") or "") if isinstance(provider, dict) else "",
        )
    finally:
        connection.close()


def ccswitch_diagnostic() -> dict:
    snapshot = read_ccswitch_snapshot(fetch_balance=False)
    root = _ccswitch_root()
    return {
        "path": str(root / "cc-switch.db"),
        "provider_name": snapshot.provider_name,
        "provider_id": snapshot.provider_id,
        "status": snapshot.status,
        "status_detail": snapshot.status_detail,
        "quota_query_enabled": snapshot.quota_query_enabled,
        "request_count": snapshot.request_count,
        "data_source": snapshot.data_source,
    }
