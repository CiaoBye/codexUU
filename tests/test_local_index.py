import json
import sqlite3
from pathlib import Path

from app.data.local_index import clear_local_index, iter_indexed_claude_events, local_index_status


def _write_event(path: Path, timestamp: str, *, tokens: int = 0, tool: str = "", skill: str = ""):
    content = []
    if tool:
        content.append({"tool_use": {"name": tool}})
    if skill:
        content.append({"skill": skill})
    record = {
        "timestamp": timestamp,
        "message": {
            "model": "claude-sonnet-test",
            "usage": {
                "input_tokens": tokens,
                "cache_read_input_tokens": tokens // 2,
                "output_tokens": tokens // 4,
            },
            "content": content,
        },
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def test_local_index_is_incremental_and_stores_only_derived_events(tmp_path):
    root = tmp_path / "projects"
    source = root / "demo" / "thread.jsonl"
    source.parent.mkdir(parents=True)
    database = tmp_path / "analytics.sqlite"
    _write_event(source, "2026-07-14T01:00:00Z", tokens=100, tool="Bash", skill="review")

    first = list(iter_indexed_claude_events(root, database))
    assert len(first) == 1
    assert first[0].project == "demo"
    assert first[0].uncached_input == 100
    assert first[0].cached_input == 50
    assert first[0].tools == ("Bash",)
    assert first[0].skills == ("review",)
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT model, tools_json, skills_json FROM claude_index_events"
        ).fetchone()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(claude_index_events)")}
    assert stored == ("claude-sonnet-test", '["Bash"]', '["review"]')
    assert "message" not in columns
    assert "event_json" not in columns

    _write_event(source, "2026-07-14T02:00:00Z", tokens=80, tool="Read")
    second = list(iter_indexed_claude_events(root, database, force_sync=True))
    assert len(second) == 2
    status = local_index_status(database)
    assert status.available is True
    assert status.file_count == 1
    assert status.event_count == 2


def test_clear_local_index_removes_database_and_sqlite_sidecars(tmp_path):
    database = tmp_path / "analytics.sqlite"
    for path in (database, tmp_path / "analytics.sqlite-wal", tmp_path / "analytics.sqlite-shm"):
        path.write_text("derived data", encoding="utf-8")

    clear_local_index(database)

    assert not database.exists()
    assert not (tmp_path / "analytics.sqlite-wal").exists()
    assert not (tmp_path / "analytics.sqlite-shm").exists()
