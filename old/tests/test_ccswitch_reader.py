import json
import sqlite3
from datetime import datetime, timedelta, timezone

from app.data import ccswitch_reader
from app.utils.statistics_timezone import configure_statistics_timezone


def _create_ccswitch_db(root, provider_meta=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text(
        json.dumps({"currentProviderCodex": "provider-1"}), encoding="utf-8"
    )
    connection = sqlite3.connect(root / "cc-switch.db")
    connection.executescript(
        """
        CREATE TABLE providers (
            id TEXT, app_type TEXT, name TEXT, settings_config TEXT,
            meta TEXT, provider_type TEXT, is_current INTEGER, created_at INTEGER
        );
        CREATE TABLE proxy_request_logs (
            request_id TEXT, provider_id TEXT, app_type TEXT, model TEXT,
            input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER,
            total_cost_usd TEXT, status_code INTEGER, created_at INTEGER
        );
        CREATE TABLE usage_daily_rollups (
            date TEXT, app_type TEXT, provider_id TEXT, input_tokens INTEGER,
            output_tokens INTEGER, cache_read_tokens INTEGER, total_cost_usd TEXT,
            request_count INTEGER, success_count INTEGER
        );
        """
    )
    meta = provider_meta or {}
    connection.execute(
        "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "provider-1", "codex", "Relay Test", json.dumps({
                "auth": {"OPENAI_API_KEY": "test-key"},
                "config": "OPENAI_BASE_URL=https://relay.example",
            }), json.dumps(meta), None, 1, 0,
        ),
    )
    connection.commit()
    return connection


def _usage_meta(enabled=True):
    return {
        "usage_script": {
            "enabled": enabled,
            "timeout": 5,
            "autoQueryInterval": 30,
            "code": """({
                request: { url: \"{{baseUrl}}/v1/usage\", method: \"GET\", headers: {
                    \"Authorization\": \"Bearer {{apiKey}}\"
                }},
                extractor: function(response) { return { remaining: response.balance, unit: \"USD\" }; }
            })""",
        }
    }


def test_ccswitch_snapshot_reads_provider_balance_and_local_usage(tmp_path, monkeypatch):
    configure_statistics_timezone("fixed", "Asia/Shanghai")
    connection = _create_ccswitch_db(tmp_path / ".cc-switch", _usage_meta())
    now = datetime.now(timezone.utc)
    connection.executemany(
        "INSERT INTO proxy_request_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("one", "provider-1", "codex", "relay-model", 100, 20, 40, "0.25", 200, int(now.timestamp())),
            ("two", "provider-1", "codex", "relay-model", 80, 10, 20, "0.10", 429, int((now - timedelta(minutes=2)).timestamp())),
        ],
    )
    connection.commit()
    connection.close()

    class Response:
        status_code = 200

        def json(self):
            return {"balance": 34.66, "unit": "USD", "planName": "Pro", "isValid": True}

    calls = []

    def request(method, url, headers, timeout):
        calls.append((method, url, headers, timeout))
        return Response()

    monkeypatch.setattr(ccswitch_reader.requests, "request", request)
    snapshot = ccswitch_reader.read_ccswitch_snapshot(tmp_path / ".cc-switch")

    assert snapshot.provider_name == "Relay Test"
    assert snapshot.balance.remaining == 34.66
    assert snapshot.balance.unit == "USD"
    assert snapshot.plan_name == "Pro"
    assert snapshot.tokens.today.total == 210
    assert snapshot.tokens.today.cached_input == 60
    assert snapshot.tokens.today.uncached_input == 120
    assert snapshot.request_count == 2
    assert snapshot.success_count == 1
    assert snapshot.failure_count == 1
    assert snapshot.total_cost_usd == 0.35
    assert calls == [("GET", "https://relay.example/v1/usage", {
        "Accept": "application/json", "Authorization": "Bearer test-key",
    }, 5)]
    configure_statistics_timezone("system")


def test_ccswitch_balance_failure_keeps_token_usage_and_does_not_invent_quota(tmp_path, monkeypatch):
    connection = _create_ccswitch_db(tmp_path / ".cc-switch", _usage_meta())
    now = datetime.now(timezone.utc)
    connection.execute(
        "INSERT INTO proxy_request_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("one", "provider-1", "codex", "relay-model", 100, 20, 40, "0.25", 200, int(now.timestamp())),
    )
    connection.commit()
    connection.close()

    def request(*_args, **_kwargs):
        raise ccswitch_reader.requests.Timeout("test timeout")

    monkeypatch.setattr(ccswitch_reader.requests, "request", request)
    snapshot = ccswitch_reader.read_ccswitch_snapshot(tmp_path / ".cc-switch")

    assert snapshot.balance is None
    assert snapshot.tokens.today.total == 120
    assert snapshot.status == ccswitch_reader.PROVIDER_STATUS_DEGRADED
    assert "接口失败" in snapshot.status_detail


def test_ccswitch_without_usage_script_is_still_usable_for_local_tokens(tmp_path):
    connection = _create_ccswitch_db(tmp_path / ".cc-switch", _usage_meta(enabled=False))
    now = datetime.now(timezone.utc)
    connection.execute(
        "INSERT INTO proxy_request_logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("one", "provider-1", "codex", "relay-model", 100, 20, 40, "0.25", 200, int(now.timestamp())),
    )
    connection.commit()
    connection.close()

    snapshot = ccswitch_reader.read_ccswitch_snapshot(tmp_path / ".cc-switch")

    assert snapshot.balance is None
    assert snapshot.quota_query_enabled is False
    assert snapshot.tokens.today.total == 120
    assert snapshot.status == ccswitch_reader.PROVIDER_STATUS_AVAILABLE


def test_ccswitch_provider_parse_failure_returns_unavailable_snapshot(tmp_path, monkeypatch):
    connection = _create_ccswitch_db(tmp_path / ".cc-switch")
    connection.close()
    monkeypatch.setattr(
        ccswitch_reader,
        "_provider_row",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("broken provider")),
    )

    snapshot = ccswitch_reader.read_ccswitch_snapshot(tmp_path / ".cc-switch")

    assert snapshot.status == ccswitch_reader.PROVIDER_STATUS_UNAVAILABLE
    assert snapshot.provider_id == ""
    assert snapshot.provider_name == ""
    assert "ValueError" in snapshot.status_detail
