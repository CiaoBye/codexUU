from datetime import datetime, timedelta, timezone
from pathlib import Path

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
