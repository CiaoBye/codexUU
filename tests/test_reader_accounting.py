from datetime import datetime, timedelta, timezone
from pathlib import Path
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


def test_store_app_alias_does_not_block_quota_refresh(monkeypatch):
    monkeypatch.setattr(codex_reader.shutil, "which", lambda _: r"C:\Program Files\WindowsApps\codex.exe")
    assert codex_reader.read_quota_from_appserver() is None


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
