from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from app.data.models import parse_jsonl_line


INDEX_DIR = Path.home() / ".codexU"
INDEX_FILE = INDEX_DIR / "analytics.sqlite"
_SYNC_TTL_SECONDS = 8
_recent_sync: dict[tuple[str, str], float] = {}


@dataclass(frozen=True)
class IndexedClaudeEvent:
    path: Path
    project: str
    modified_at: datetime
    timestamp: Optional[datetime]
    model: str
    uncached_input: int
    cached_input: int
    output: int
    tools: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalIndexStatus:
    available: bool
    file_count: int = 0
    event_count: int = 0
    last_scan: Optional[datetime] = None


def _database_path(database: Optional[Path] = None) -> Path:
    return database or INDEX_FILE


def _connect(database: Optional[Path] = None) -> sqlite3.Connection:
    path = _database_path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=3)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS claude_index_files (
            path TEXT PRIMARY KEY,
            mtime_ns INTEGER NOT NULL,
            size INTEGER NOT NULL,
            project TEXT NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS claude_index_events (
            path TEXT NOT NULL,
            line_no INTEGER NOT NULL,
            timestamp TEXT,
            model TEXT NOT NULL DEFAULT '',
            uncached_input INTEGER NOT NULL DEFAULT 0,
            cached_input INTEGER NOT NULL DEFAULT 0,
            output INTEGER NOT NULL DEFAULT 0,
            tools_json TEXT NOT NULL DEFAULT '[]',
            skills_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY(path, line_no)
        );
        CREATE INDEX IF NOT EXISTS idx_claude_index_events_path ON claude_index_events(path);
        CREATE TABLE IF NOT EXISTS local_index_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        """
    )
    return connection


def _parse_timestamp(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _content_blocks(event: dict) -> list[dict]:
    message = event.get("message", {})
    content = message.get("content", []) if isinstance(message, dict) else []
    return [block for block in content if isinstance(block, dict)] if isinstance(content, list) else []


def _event_row(event: dict, path: Path, line_no: int) -> Optional[tuple]:
    message = event.get("message", {})
    usage = message.get("usage") if isinstance(message, dict) else None
    cached_input = 0
    uncached_input = 0
    output = 0
    model = ""
    if isinstance(usage, dict):
        cached_input = int(usage.get("cached_input_tokens", 0) or 0)
        cached_input += int(usage.get("cache_read_input_tokens", 0) or 0)
        cached_input += int(usage.get("cache_creation_input_tokens", 0) or 0)
        uncached_input = int(usage.get("input_tokens", 0) or 0)
        output = int(usage.get("output_tokens", 0) or 0)
        model = str(message.get("model", "") or "")
    tools: list[str] = []
    skills: list[str] = []
    for block in _content_blocks(event):
        tool = block.get("tool_use")
        if isinstance(tool, dict) and isinstance(tool.get("name"), str):
            tools.append(tool["name"])
        if isinstance(block.get("skill"), str):
            skills.append(block["skill"])
    if not any((uncached_input, cached_input, output, tools, skills)):
        return None
    return (
        str(path), line_no, str(event.get("timestamp") or event.get("created_at") or ""), model,
        max(0, uncached_input), max(0, cached_input), max(0, output),
        json.dumps(tools, ensure_ascii=False), json.dumps(skills, ensure_ascii=False),
    )


def _sync_claude(root: Path, database: Optional[Path] = None, force: bool = False) -> None:
    root = root.expanduser()
    database_path = _database_path(database)
    cache_key = (str(root.resolve()) if root.exists() else str(root), str(database_path.resolve()))
    now_monotonic = time.monotonic()
    if not force and now_monotonic - _recent_sync.get(cache_key, 0) < _SYNC_TTL_SECONDS:
        return
    _recent_sync[cache_key] = now_monotonic
    files = sorted(root.rglob("*.jsonl")) if root.exists() else []
    scan_time = datetime.now(timezone.utc).isoformat()
    with _connect(database) as connection:
        known = {
            row[0]: (int(row[1]), int(row[2]))
            for row in connection.execute("SELECT path, mtime_ns, size FROM claude_index_files")
        }
        seen: set[str] = set()
        for path in files:
            try:
                stat = path.stat()
                resolved = path.resolve()
            except OSError:
                continue
            key = str(resolved)
            seen.add(key)
            signature = (stat.st_mtime_ns, stat.st_size)
            if known.get(key) == signature:
                continue
            try:
                relative = resolved.relative_to(root.resolve())
                project = relative.parts[0] if len(relative.parts) > 1 else "default"
                rows = []
                with resolved.open("r", encoding="utf-8", errors="ignore") as handle:
                    for line_no, line in enumerate(handle, start=1):
                        event = parse_jsonl_line(line)
                        if event:
                            row = _event_row(event, resolved, line_no)
                            if row:
                                rows.append(row)
            except (OSError, UnicodeError, RuntimeError):
                continue
            connection.execute("DELETE FROM claude_index_events WHERE path = ?", (key,))
            connection.execute("DELETE FROM claude_index_files WHERE path = ?", (key,))
            connection.execute(
                "INSERT INTO claude_index_files(path, mtime_ns, size, project, indexed_at) VALUES (?, ?, ?, ?, ?)",
                (key, stat.st_mtime_ns, stat.st_size, project, scan_time),
            )
            if rows:
                connection.executemany(
                    "INSERT INTO claude_index_events(path, line_no, timestamp, model, uncached_input, cached_input, output, tools_json, skills_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows,
                )
        for stale in set(known) - seen:
            connection.execute("DELETE FROM claude_index_events WHERE path = ?", (stale,))
            connection.execute("DELETE FROM claude_index_files WHERE path = ?", (stale,))
        connection.execute(
            "INSERT INTO local_index_meta(key, value) VALUES ('claude_last_scan', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (scan_time,),
        )


def iter_indexed_claude_events(
    root: Path, database: Optional[Path] = None, *, force_sync: bool = False,
) -> Iterator[IndexedClaudeEvent]:
    """Yield compact local analytics records without retaining transcript text."""
    _sync_claude(root, database, force=force_sync)
    with _connect(database) as connection:
        rows = connection.execute(
            "SELECT files.path, files.project, files.mtime_ns, events.timestamp, events.model, "
            "events.uncached_input, events.cached_input, events.output, events.tools_json, events.skills_json "
            "FROM claude_index_events AS events JOIN claude_index_files AS files ON files.path = events.path "
            "ORDER BY events.timestamp"
        )
        for path, project, mtime_ns, timestamp, model, uncached, cached, output, tools, skills in rows:
            try:
                modified = datetime.fromtimestamp(int(mtime_ns) / 1_000_000_000, tz=timezone.utc)
                tool_names = tuple(item for item in json.loads(tools) if isinstance(item, str))
                skill_names = tuple(item for item in json.loads(skills) if isinstance(item, str))
            except (ValueError, TypeError, json.JSONDecodeError, OSError):
                continue
            yield IndexedClaudeEvent(
                path=Path(path), project=project, modified_at=modified, timestamp=_parse_timestamp(timestamp),
                model=str(model or ""), uncached_input=int(uncached or 0), cached_input=int(cached or 0),
                output=int(output or 0), tools=tool_names, skills=skill_names,
            )


def local_index_status(database: Optional[Path] = None) -> LocalIndexStatus:
    path = _database_path(database)
    if not path.exists():
        return LocalIndexStatus(False)
    try:
        with _connect(database) as connection:
            file_count = int(connection.execute("SELECT COUNT(*) FROM claude_index_files").fetchone()[0])
            event_count = int(connection.execute("SELECT COUNT(*) FROM claude_index_events").fetchone()[0])
            row = connection.execute("SELECT value FROM local_index_meta WHERE key = 'claude_last_scan'").fetchone()
        return LocalIndexStatus(True, file_count, event_count, _parse_timestamp(row[0]) if row else None)
    except sqlite3.Error:
        return LocalIndexStatus(False)


def clear_local_index(database: Optional[Path] = None) -> None:
    """Delete only derived analytics records; raw Codex/Claude logs remain untouched."""
    path = _database_path(database)
    if path.exists():
        path.unlink()
    _recent_sync.clear()
