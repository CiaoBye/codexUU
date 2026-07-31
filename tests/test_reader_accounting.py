from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from queue import Queue
import sqlite3

from app.data import codex_reader
from app.data.codex_reader import _delta_breakdown
from app.data.models import DailyToken, TokenBreakdown
from app.utils.statistics_timezone import configure_statistics_timezone


def test_cumulative_token_snapshots_are_delta_counted():
    previous = TokenBreakdown(cached_input=100, uncached_input=200, output=30)
    current = TokenBreakdown(cached_input=140, uncached_input=260, output=45)
    assert _delta_breakdown(previous, current).total == 115


def test_cumulative_token_reset_starts_new_session():
    previous = TokenBreakdown(cached_input=100, uncached_input=200, output=30)
    current = TokenBreakdown(cached_input=10, uncached_input=20, output=4)
    assert _delta_breakdown(previous, current).total == 34


def test_turn_context_exposes_model_effort_and_turn_id():
    model, effort, turn_id = codex_reader._model_context_from_event({
        "type": "turn_context",
        "payload": {"model": "gpt-5.6-sol", "effort": "medium", "turn_id": "turn-1"},
    })
    assert (model, effort, turn_id) == ("gpt-5.6-sol", "medium", "turn-1")


def test_model_usage_keeps_model_effort_token_and_daily_attribution(monkeypatch):
    now = datetime.now(timezone.utc)
    events = [
        (Path("one.jsonl"), now, now.isoformat(), TokenBreakdown(10, 20, 5), {
            "_codexu_model": "gpt-5.6-terra", "_codexu_effort": "high", "_codexu_turn_id": "t1",
        }),
        (Path("one.jsonl"), now, now.isoformat(), TokenBreakdown(5, 10, 2), {
            "_codexu_model": "gpt-5.6-terra", "_codexu_effort": "high", "_codexu_turn_id": "t2",
        }),
    ]
    monkeypatch.setattr(codex_reader, "_cached", lambda _: None)
    monkeypatch.setattr(codex_reader, "_store", lambda _key, value: value)
    monkeypatch.setattr(codex_reader, "_iter_token_deltas", lambda days=180: iter(events))
    result = codex_reader.read_model_usage()
    assert len(result) == 1
    assert result[0].name == "gpt-5.6-terra"
    assert result[0].effort == "high"
    assert result[0].token_total == 52
    assert result[0].session_count == 1
    assert result[0].turn_count == 2
    assert result[0].daily_tokens[0].total == 52


def test_branch_token_prefix_is_deduplicated_with_child_high_water_mark(monkeypatch):
    parent = Path("parent.jsonl")
    child = Path("child.jsonl")

    def token(total, last):
        return {
            "timestamp": f"2026-07-30T00:{total // 10:02d}:00+00:00",
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": total,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": total,
                    },
                    "last_token_usage": {
                        "input_tokens": last,
                        "cached_input_tokens": 0,
                        "output_tokens": 0,
                        "total_tokens": last,
                    },
                },
            },
        }

    parent_events = [
        {"type": "session_meta", "payload": {"id": "parent-thread"}},
        token(100, 100), token(160, 60), token(240, 80),
    ]
    child_events = [
        {"type": "session_meta", "payload": {"id": "child-thread", "parent_thread_id": "parent-thread"}},
        token(100, 100), token(160, 60), token(240, 80), token(275, 35),
    ]
    monkeypatch.setattr(codex_reader, "_cached", lambda _key: None)
    monkeypatch.setattr(codex_reader, "_store", lambda _key, value: value)
    monkeypatch.setattr(codex_reader, "_iter_rollout_events", lambda days=None: iter([
        (parent, datetime.now(timezone.utc), event) for event in parent_events
    ] + [
        (child, datetime.now(timezone.utc), event) for event in child_events
    ]))

    records = list(codex_reader._iter_token_deltas())

    assert [item[3].total for item in records] == [100, 60, 80, 35]
    assert sum(item[3].total for item in records) == 275


def test_unrelated_token_sequences_are_not_deduplicated():
    assert codex_reader._inherited_prefix_length(
        ["same", "different"], ["same", "parent-only"],
    ) == 1
    assert codex_reader._inherited_prefix_length(["only-child"], ["only-parent"]) == 0


def test_rollout_reader_skips_corrupt_lines_and_fails_closed_on_overflow(monkeypatch, tmp_path):
    path = tmp_path / "rollout-test.jsonl"
    path.write_text('{"type":"one"}\nnot-json\n{"type":"two"}\n', encoding="utf-8")
    stat = path.stat()
    events = codex_reader._read_rollout_file_events(path, stat, datetime.now(timezone.utc))
    assert [event["type"] for event in events] == ["one", "two"]

    monkeypatch.setattr(codex_reader, "_MAX_ROLLOUT_LINES", 2)
    path.write_text('{"type":"one"}\n{"type":"two"}\n{"type":"three"}\n', encoding="utf-8")
    assert codex_reader._read_rollout_file_events(path, path.stat(), datetime.now(timezone.utc)) == []
    assert path not in codex_reader._rollout_file_cache


def test_token_reader_rejects_negative_or_unreasonably_large_values():
    event = {
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {"total_token_usage": {"input_tokens": -1}},
        },
    }
    assert codex_reader._read_token_event(event) is None
    event["payload"]["info"]["total_token_usage"]["input_tokens"] = 10**16
    assert codex_reader._read_token_event(event) is None


def test_aggregate_cache_has_a_hard_entry_limit(monkeypatch):
    cache = {}
    monkeypatch.setattr(codex_reader, "_cache", cache)
    for index in range(codex_reader._CACHE_LIMIT + 10):
        codex_reader._store(f"key-{index}", index)
    assert len(cache) == codex_reader._CACHE_LIMIT


def test_snapshot_uses_detailed_daily_tokens_for_today_and_week(monkeypatch):
    configure_statistics_timezone("utc")
    today = datetime.now(timezone.utc)
    daily = [
        DailyToken(date=today, total=60, cached_input=20, uncached_input=30, output=10),
        DailyToken(date=today - timedelta(days=3), total=40, cached_input=10, uncached_input=20, output=10),
        DailyToken(date=today - timedelta(days=10), total=25, cached_input=5, uncached_input=15, output=5),
    ]
    monkeypatch.setattr(codex_reader, "read_quota_from_appserver", lambda: None)
    monkeypatch.setattr(codex_reader, "read_quota_from_session_events", lambda: None)
    monkeypatch.setattr(codex_reader, "read_token_totals_from_db", lambda: None)
    monkeypatch.setattr(codex_reader, "read_session_tokens", lambda: TokenBreakdown(100, 200, 50))
    monkeypatch.setattr(codex_reader, "read_daily_tokens", lambda: daily)
    monkeypatch.setattr(codex_reader, "read_thread_index_token_total", lambda: 360)
    monkeypatch.setattr(codex_reader, "read_model_priced_values", lambda: {
        "today": 1.0, "rolling_week": 2.0, "week": 1.5, "month": 3.0, "cumulative": 4.0,
        "coverage_pct": 75.0, "unpriced_tokens": 25,
    })

    snapshot = codex_reader.read_codex_snapshot()
    assert snapshot.tokens.today.total == 60
    assert snapshot.tokens.last_7d.total == 100
    expected_week = sum(
        item.total for item in daily
        if item.date.date() >= today.date() - timedelta(days=today.weekday())
    )
    assert snapshot.tokens.current_week.total == expected_week
    assert snapshot.current_week_api_equivalent_value == 1.5
    assert snapshot.tokens.cumulative.total == 350
    expected_month = sum(item.total for item in daily if item.date.month == today.month and item.date.year == today.year)
    assert snapshot.tokens.current_month.total == expected_month
    assert snapshot.cumulative_index_total == 360
    configure_statistics_timezone("system")


def test_snapshot_exposes_monthly_quota_without_relabeling_it_as_seven_day(monkeypatch):
    monthly = codex_reader.QuotaInfo(
        used_pct=35,
        remaining_pct=65,
        window_minutes=43800,
    )
    monkeypatch.setattr(codex_reader, "read_quota_from_appserver", lambda: (None, None))
    monkeypatch.setattr(codex_reader, "get_last_quota_windows", lambda: codex_reader.QuotaWindows(monthly=monthly, authoritative=True))
    monkeypatch.setattr(codex_reader, "read_token_totals_from_db", lambda: None)
    monkeypatch.setattr(codex_reader, "read_session_tokens", lambda: TokenBreakdown())
    monkeypatch.setattr(codex_reader, "read_daily_tokens", lambda: [])
    monkeypatch.setattr(codex_reader, "read_model_priced_values", lambda: {
        "today": 0.0, "rolling_week": 0.0, "week": 0.0, "month": 0.0,
        "cumulative": 0.0, "coverage_pct": 0.0, "unpriced_tokens": 0,
    })

    snapshot = codex_reader.read_codex_snapshot()

    assert snapshot.quota_7d is None
    assert snapshot.quota_month is monthly


def test_store_app_alias_does_not_block_quota_refresh(monkeypatch):
    monkeypatch.setattr(codex_reader.shutil, "which", lambda _: r"C:\Program Files\WindowsApps\codex.exe")
    monkeypatch.setattr(codex_reader, "_codex_dir", lambda: Path("missing-codex-dir"))
    assert codex_reader.read_quota_from_appserver() is None


def test_appserver_prefers_current_codex_bucket_and_preserves_reset_time(monkeypatch, tmp_path):
    runtime = tmp_path / "codex.exe"
    runtime.touch()
    monkeypatch.setattr(codex_reader, "_live_quota_cache", None)
    monkeypatch.setattr(codex_reader, "_appserver_executables", lambda: [str(runtime)])
    monkeypatch.setattr(codex_reader, "_appserver_rate_limits", lambda _: {
        "rateLimits": {"limitId": "other", "primary": None, "secondary": None},
        "rateLimitsByLimitId": {
            "codex": {"limitId": "codex", "primary": {
                "usedPercent": 100, "windowDurationMins": 10080, "resetsAt": 1_800_000_000,
            }, "secondary": None},
        },
    })

    q5, q7 = codex_reader.read_quota_from_appserver()
    assert q5 is None
    assert q7.used_pct == 100
    assert q7.reset_time is not None
    assert codex_reader.get_last_quota_status() == "available"


def test_live_appserver_quota_is_reused_between_scheduled_refreshes(monkeypatch):
    quota = (None, codex_reader.QuotaInfo(used_pct=100, remaining_pct=0))
    monkeypatch.setattr(codex_reader, "_live_quota_cache", (codex_reader.time.monotonic(), quota, "available"))
    class LiveSession:
        is_alive = True
    monkeypatch.setattr(codex_reader, "_appserver_session", LiveSession())
    monkeypatch.setattr(codex_reader, "_appserver_executables", lambda: (_ for _ in ()).throw(AssertionError("must not spawn")))

    assert codex_reader.read_quota_from_appserver() == quota


def test_dead_runtime_does_not_reuse_stale_live_quota(monkeypatch):
    quota = (None, codex_reader.QuotaInfo(used_pct=100, remaining_pct=0))
    monkeypatch.setattr(codex_reader, "_live_quota_cache", (codex_reader.time.monotonic(), quota, "available"))

    class DeadSession:
        is_alive = False

    monkeypatch.setattr(codex_reader, "_appserver_session", DeadSession())
    monkeypatch.setattr(codex_reader, "_appserver_executables", lambda: ["runtime"])
    monkeypatch.setattr(codex_reader, "_appserver_rate_limits", lambda _: None)

    assert codex_reader.read_quota_from_appserver() is None
    assert codex_reader.get_last_quota_status() == "unavailable"


def test_appserver_quota_reader_hides_windows_console(monkeypatch):
    captured = {}

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        raise OSError("test")

    monkeypatch.setattr(codex_reader.os, "name", "nt")
    monkeypatch.setattr(codex_reader.subprocess, "Popen", fake_popen)

    assert codex_reader._appserver_rate_limits("codex.exe") is None
    assert captured["creationflags"] == getattr(codex_reader.subprocess, "CREATE_NO_WINDOW", 0x08000000)


def test_appserver_protocol_handshake_and_requests_reuse_one_process(monkeypatch):
    class FakeStdout:
        def __init__(self):
            self.lines = Queue()

        def push(self, message):
            self.lines.put(json.dumps(message) + "\n")

        def close(self):
            self.lines.put(None)

        def __iter__(self):
            while True:
                line = self.lines.get()
                if line is None:
                    return
                yield line

    class FakeStdin:
        def __init__(self, stdout):
            self.stdout = stdout

        def write(self, line):
            request = json.loads(line)
            if request.get("method") == "initialize":
                self.stdout.push({"jsonrpc": "2.0", "id": request["id"], "result": {}})
            elif request.get("method") == "account/rateLimits/read":
                self.stdout.push({"jsonrpc": "2.0", "id": request["id"], "result": {"rateLimits": {}}})
            elif request.get("method") == "thread/list":
                self.stdout.push({"jsonrpc": "2.0", "id": request["id"], "result": {"data": []}})

        def flush(self):
            return None

        def close(self):
            return None

    class FakeProcess:
        def __init__(self):
            self.stdout = FakeStdout()
            self.stdin = FakeStdin(self.stdout)
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 0
            self.stdout.close()

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.terminate()

    started = []

    def fake_popen(*args, **kwargs):
        started.append((args, kwargs))
        return FakeProcess()

    monkeypatch.setattr(codex_reader.subprocess, "Popen", fake_popen)
    session = codex_reader._CodexAppServerSession()
    try:
        assert session.request("runtime", "account/rateLimits/read", None) == {"rateLimits": {}}
        assert session.request("runtime", "thread/list", {"limit": 1}) == {"data": []}
        assert len(started) == 1
        assert started[0][0][0] == ["runtime", "app-server", "--stdio"]
    finally:
        session.close()


def test_appserver_diagnostics_exposes_connection_state_and_error():
    session = codex_reader._CodexAppServerSession()
    assert session.diagnostics()["status"] == codex_reader.RUNTIME_STATUS_UNAVAILABLE
    session._set_status(codex_reader.RUNTIME_STATUS_TIMEOUT, "test timeout")
    snapshot = session.diagnostics()
    assert snapshot["status"] == codex_reader.RUNTIME_STATUS_TIMEOUT
    assert snapshot["last_error"] == "test timeout"


def test_task_board_uses_live_runtime_threads_before_sqlite(monkeypatch, tmp_path):
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(codex_reader, "_cached", lambda _: None)
    class FakeSession:
        is_alive = True
    monkeypatch.setattr(codex_reader, "_appserver_session", FakeSession())
    monkeypatch.setattr(codex_reader, "_appserver_executables", lambda: ["runtime"])
    monkeypatch.setattr(codex_reader, "_appserver_thread_list", lambda _: [{
        "id": "thread-1",
        "title": "Live task",
        "preview": "Live preview",
        "cwd": r"C:\\Work\\demo",
        "archived": False,
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
        "recencyAt": now.isoformat(),
        "archivedAt": None,
    }])
    monkeypatch.setattr(codex_reader, "_state_db_path", lambda: (_ for _ in ()).throw(AssertionError("must use runtime")))
    monkeypatch.setattr(codex_reader, "_automations_dir", lambda: tmp_path / "automations")

    result = codex_reader.read_task_board()

    assert len(result) == 1
    assert result[0].id == "thread-1"
    assert result[0].status == "running"
    assert result[0].project == "demo"


def test_archived_at_is_authoritative_for_runtime_task_completion():
    now = datetime.now(timezone.utc)
    item = codex_reader._tasks_from_runtime_rows([{
        "id": "thread-archived",
        "name": "Archived task",
        "cwd": r"C:\\Work\\demo",
        "archived": False,
        "createdAt": now.isoformat(),
        "updatedAt": now.isoformat(),
        "recencyAt": now.isoformat(),
        "archivedAt": (now - timedelta(minutes=5)).isoformat(),
    }], now)[0]

    assert item.status == "completed"
    assert item.updated_at == now - timedelta(minutes=5)


def test_quota_and_tasks_share_runtime_session(monkeypatch):
    calls = []

    class FakeSession:
        def request(self, executable, method, params):
            calls.append((executable, method, params))
            if method == "account/rateLimits/read":
                return {"rateLimits": {"primary": None, "secondary": None}}
            return {"data": []}

    monkeypatch.setattr(codex_reader, "_appserver_session", FakeSession())

    assert codex_reader._appserver_rate_limits("runtime") is not None
    assert codex_reader._appserver_thread_list("runtime") == []
    assert [method for _, method, _ in calls] == ["account/rateLimits/read", "thread/list"]


def test_project_directory_accepts_current_project_and_rejects_deleted_or_dated_workspace(tmp_path):
    assert codex_reader._project_directory(Path.cwd()) == Path.cwd().resolve()
    assert codex_reader._project_directory(tmp_path / "deleted") is None
    dated = tmp_path / "2026-07-06" / "chat"
    dated.mkdir(parents=True)
    (dated / "note.txt").write_text("one-off", encoding="utf-8")
    assert codex_reader._project_directory(dated) is None


def test_current_rate_limit_schema_maps_windows_by_duration():
    q5, q7 = codex_reader._quota_pair_from_rate_limits({
        "primary": {"usedPercent": 20, "windowDurationMins": 300, "resetsAt": 1_800_000_000},
        "secondary": {"usedPercent": 35, "windowDurationMins": 10080, "resetsAt": 1_800_010_000},
    })
    assert q5.remaining_pct == 80
    assert q7.remaining_pct == 65


def test_rate_limit_normalizer_ignores_slot_order_and_supports_monthly_window():
    normalized = codex_reader._normalize_rate_limits({
        "primary": {"usedPercent": 35, "windowDurationMins": 43800, "resetsAt": 1_800_000_000},
        "secondary": {"usedPercent": 20, "windowDurationMins": 300, "resetsAt": 1_800_001_000},
    })

    assert normalized.five_hour.window_minutes == 300
    assert normalized.monthly.window_minutes == 43800
    assert normalized.seven_day is None
    assert normalized.authoritative is True


def test_monthly_only_rate_limit_is_available_without_filling_seven_day_slot():
    normalized = codex_reader._normalize_rate_limits({
        "primary": {"usedPercent": 35, "windowDurationMins": 43800},
    })

    assert normalized.pair == (None, None)
    assert normalized.monthly is not None
    assert codex_reader._status_from_rate_limits(
        {"primary": {"windowDurationMins": 43800}},
        normalized.pair,
        normalized.authoritative,
        normalized.monthly,
    ) == "available"


def test_rate_limit_normalizer_fails_closed_for_unknown_or_duplicate_windows():
    unknown = codex_reader._normalize_rate_limits({
        "primary": {"usedPercent": 20, "windowDurationMins": 1440},
    })
    duplicate = codex_reader._normalize_rate_limits({
        "primary": {"usedPercent": 20, "windowDurationMins": 300},
        "secondary": {"usedPercent": 21, "windowDurationMins": 300},
    })

    assert unknown.five_hour is None
    assert unknown.unclassified_count == 1
    assert unknown.authoritative is False
    assert duplicate.five_hour is None
    assert duplicate.duplicate_count == 1
    assert duplicate.authoritative is False


def test_rate_limit_normalizer_checks_extra_duration_window_even_with_named_slots():
    normalized = codex_reader._normalize_rate_limits({
        "5h": {"usedPercent": 20, "windowDurationMins": 300},
        "7d": {"usedPercent": 30, "windowDurationMins": 10080},
        "tertiary": {"usedPercent": 40, "windowDurationMins": 1440},
    })

    assert normalized.unclassified_count == 1
    assert normalized.five_hour is not None
    assert normalized.seven_day is not None
    assert normalized.authoritative is False


def test_partial_known_rate_limit_is_marked_unavailable_instead_of_trusted():
    limits = {
        "primary": {"usedPercent": 20, "windowDurationMins": 10080},
        "secondary": {"usedPercent": 30, "windowDurationMins": 1440},
    }
    normalized = codex_reader._normalize_rate_limits(limits)

    assert normalized.seven_day is not None
    assert codex_reader._status_from_rate_limits(
        limits, normalized.pair, normalized.authoritative,
    ) == "unavailable"


def test_reader_hides_partial_rate_limit_windows_in_fail_closed_mode(monkeypatch):
    class LiveSession:
        is_alive = False

    monkeypatch.setattr(codex_reader, "_live_quota_cache", None)
    monkeypatch.setattr(codex_reader, "_appserver_session", LiveSession())
    monkeypatch.setattr(codex_reader, "_appserver_executables", lambda: ["runtime"])
    monkeypatch.setattr(codex_reader, "_appserver_rate_limits", lambda _: {
        "rateLimits": {
            "primary": {"usedPercent": 20, "windowDurationMins": 10080},
            "secondary": {"usedPercent": 30, "windowDurationMins": 1440},
        }
    })

    assert codex_reader.read_quota_from_appserver() == (None, None)
    assert codex_reader.get_last_quota_windows().authoritative is False
    assert codex_reader.get_last_quota_windows().seven_day is None


def test_snapshot_does_not_revive_session_quota_after_invalid_runtime_response(monkeypatch):
    monkeypatch.setattr(codex_reader, "read_quota_from_appserver", lambda: (None, None))
    monkeypatch.setattr(codex_reader, "get_last_quota_status", lambda: "unavailable")
    monkeypatch.setattr(codex_reader, "read_quota_from_session_events", lambda: (
        codex_reader.QuotaInfo(used_pct=10, remaining_pct=90), None
    ))
    monkeypatch.setattr(codex_reader, "read_token_totals_from_db", lambda: None)
    monkeypatch.setattr(codex_reader, "read_session_tokens", lambda: TokenBreakdown())
    monkeypatch.setattr(codex_reader, "read_daily_tokens", lambda: [])
    monkeypatch.setattr(codex_reader, "read_model_priced_values", lambda: {
        "today": 0.0, "rolling_week": 0.0, "week": 0.0, "month": 0.0,
        "cumulative": 0.0, "coverage_pct": 0.0, "unpriced_tokens": 0,
    })

    snapshot = codex_reader.read_codex_snapshot()

    assert snapshot.quota_5h is None
    assert snapshot.quota_7d is None


def test_reset_credit_metadata_preserves_zero_and_full_details():
    normalized = codex_reader._normalize_rate_limits(
        {"primary": {"usedPercent": 20, "windowDurationMins": 10080, "resetsAt": 1_800_000_000}},
        reset_count=0,
        reset_times=(codex_reader._parse_reset(1_800_000_000),),
    )

    assert normalized.seven_day.reset_count == 0
    assert normalized.seven_day.reset_times == (codex_reader._parse_reset(1_800_000_000),)


def test_current_rate_limit_schema_can_honestly_return_only_seven_days():
    q5, q7 = codex_reader._quota_pair_from_rate_limits({
        "primary": {"usedPercent": 27, "windowDurationMins": 10080},
        "secondary": None,
    })
    assert q5 is None
    assert q7.remaining_pct == 73


def test_session_quota_uses_the_newest_persisted_rate_limit_snapshot(monkeypatch):
    newest = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(codex_reader, "_cached", lambda _: None)
    monkeypatch.setattr(codex_reader, "_store", lambda _key, value: value)
    monkeypatch.setattr(codex_reader, "_recent_rollout_files", lambda days, limit: [(Path("latest.jsonl"), datetime.now(timezone.utc), object())])
    monkeypatch.setattr(codex_reader, "_read_rollout_file_events", lambda *_: [{
        "timestamp": newest,
        "payload": {"rate_limits": {"primary": {"usedPercent": 31, "windowDurationMins": 10080}}},
    }])

    q5, q7 = codex_reader.read_quota_from_session_events()
    assert q5 is None
    assert q7.remaining_pct == 69


def test_session_quota_does_not_fall_back_to_stale_snapshot_when_latest_is_empty(monkeypatch):
    monkeypatch.setattr(codex_reader, "_cached", lambda _: None)
    monkeypatch.setattr(codex_reader, "_store", lambda _key, value: value)
    monkeypatch.setattr(codex_reader, "_recent_rollout_files", lambda days, limit: [
        (Path("latest.jsonl"), datetime.now(timezone.utc), object()),
        (Path("older.jsonl"), datetime.now(timezone.utc) - timedelta(days=1), object()),
    ])
    monkeypatch.setattr(codex_reader, "_read_rollout_file_events", lambda path, *_: [
        {"payload": {"rate_limits": {
            "limit_id": "codex", "primary": None, "secondary": None,
        }}}
    ] if path.name == "latest.jsonl" else [{
        "payload": {"rate_limits": {"primary": {"usedPercent": 38, "windowDurationMins": 10080}}}
    }])

    assert codex_reader.read_quota_from_session_events() == (None, None)
    assert codex_reader.get_last_quota_status() == "exhausted"


def test_empty_codex_rate_limit_snapshot_is_only_exhausted_for_explicit_codex_shape():
    assert codex_reader._status_from_rate_limits(
        {"limit_id": "codex", "primary": None, "secondary": None},
        (None, None),
    ) == "exhausted"
    assert codex_reader._status_from_rate_limits({}, (None, None)) == "unavailable"


def test_tool_usage_counts_explicit_function_call_events(monkeypatch):
    events = [
        (None, None, {"payload": {"type": "function_call", "name": "shell_command"}}),
        (None, None, {"payload": {"type": "custom_tool_call", "name": "apply_patch"}}),
        (None, None, {"payload": {"type": "function_call_output", "name": "shell_command"}}),
    ]
    monkeypatch.setattr(codex_reader, "_cached", lambda _: None)
    monkeypatch.setattr(codex_reader, "_store", lambda _key, value: value)
    monkeypatch.setattr(codex_reader, "_iter_rollout_events", lambda days=180: iter(events))

    tools = {item.name: item for item in codex_reader.read_tool_usage()}
    assert tools["shell_command"].call_count == 1
    assert tools["apply_patch"].call_count == 1
    assert all(item.estimated_value == 0 for item in tools.values())


def test_skill_usage_only_counts_explicit_skill_file_loads(monkeypatch):
    events = [
        (None, None, {"payload": {
            "type": "function_call",
            "name": "shell_command",
            "arguments": r'{"command":"Get-Content C:\\Users\\A\\.codex\\skills\\imagegen\\SKILL.md"}',
        }}),
        (None, None, {"payload": {
            "type": "function_call",
            "name": "shell_command",
            "arguments": r'{"command":"Get-Content C:\\Users\\A\\.codex\\skills\\imagegen\\SKILL.md"}',
        }}),
        (None, None, {"payload": {
            "type": "message",
            "content": "imagegen/SKILL.md",
        }}),
    ]
    monkeypatch.setattr(codex_reader, "_cached", lambda _: None)
    monkeypatch.setattr(codex_reader, "_store", lambda _key, value: value)
    monkeypatch.setattr(codex_reader, "_iter_rollout_events", lambda days=180: iter(events))

    skills = codex_reader.read_skill_usage()
    assert [(item.name, item.use_count) for item in skills] == [("imagegen", 2)]


def test_task_completion_uses_archived_at_and_active_window_is_two_hours():
    configure_statistics_timezone("utc")
    now = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = now - timedelta(days=1)
    completed = codex_reader._classify_thread_task(
        1, yesterday.timestamp(), yesterday.timestamp(), yesterday.timestamp(),
        (now - timedelta(minutes=5)).timestamp(), now,
    )
    active = codex_reader._classify_thread_task(
        0, now.timestamp(), now.timestamp(), (now - timedelta(minutes=90)).timestamp(), None, now,
    )
    pending = codex_reader._classify_thread_task(
        0, now.timestamp(), now.timestamp(), (now - timedelta(hours=3)).timestamp(), None, now,
    )
    assert completed[0] == "completed"
    assert active[0] == "running"
    assert pending[0] == "pending"
    configure_statistics_timezone("system")


def test_task_board_reads_today_archive_time_and_cleans_markdown(monkeypatch, tmp_path):
    configure_statistics_timezone("utc")
    now = datetime.now(timezone.utc)
    db = tmp_path / "state_5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT, title TEXT, preview TEXT, cwd TEXT, archived INTEGER, "
            "created_at INTEGER, updated_at INTEGER, recency_at INTEGER, archived_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("done", "[CodexUU](https://github.com/CiaoBye/codexUU)", "", str(tmp_path), 1,
             int((now - timedelta(days=2)).timestamp()), int((now - timedelta(days=2)).timestamp()),
             int((now - timedelta(days=2)).timestamp()), int((now - timedelta(minutes=3)).timestamp())),
        )
    monkeypatch.setattr(codex_reader, "_state_db_path", lambda: db)
    monkeypatch.setattr(codex_reader, "_automations_dir", lambda: tmp_path / "none")
    codex_reader.clear_cache()
    tasks = codex_reader.read_task_board()
    assert [(task.status, task.title) for task in tasks] == [("completed", "CodexUU")]
    configure_statistics_timezone("system")


def test_task_board_keeps_archived_history_sorted_by_archive_time(monkeypatch, tmp_path):
    configure_statistics_timezone("utc")
    now = datetime.now(timezone.utc)
    db = tmp_path / "state_5.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT, title TEXT, preview TEXT, cwd TEXT, archived INTEGER, "
            "created_at INTEGER, updated_at INTEGER, recency_at INTEGER, archived_at INTEGER)"
        )
        for item_id, title, minutes in (("older", "旧归档", 90), ("newer", "新归档", 5)):
            stamp = int((now - timedelta(minutes=minutes)).timestamp())
            conn.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (item_id, title, "", str(tmp_path), 1, stamp, stamp, stamp, stamp),
            )
    monkeypatch.setattr(codex_reader, "_state_db_path", lambda: db)
    monkeypatch.setattr(codex_reader, "_automations_dir", lambda: tmp_path / "none")
    codex_reader.clear_cache()
    assert [task.title for task in codex_reader.read_task_board()] == ["新归档", "旧归档"]
    configure_statistics_timezone("system")


def test_clear_cache_forces_fresh_aggregate_reads():
    codex_reader._store("probe", 1)
    assert codex_reader._cached("probe") == 1
    codex_reader.clear_cache()
    assert codex_reader._cached("probe") is None


def test_state_db_path_supports_nested_sqlite_directory(monkeypatch, tmp_path):
    nested = tmp_path / "sqlite" / "state_5.sqlite"
    nested.parent.mkdir()
    nested.touch()
    monkeypatch.setattr(codex_reader, "_codex_dir", lambda: tmp_path)
    assert codex_reader._state_db_path() == nested
