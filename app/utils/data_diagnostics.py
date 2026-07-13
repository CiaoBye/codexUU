from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class DataSourceStatus:
    name: str
    detail: str
    level: str = "ok"


def diagnose_data_sources() -> list[DataSourceStatus]:
    home = Path.home()
    codex = home / ".codex"
    sessions = codex / "sessions"
    archived = codex / "archived_sessions"
    state = codex / "state_5.sqlite"
    session_count = sum(1 for _ in sessions.rglob("*.jsonl")) if sessions.exists() else 0
    archived_count = sum(1 for _ in archived.glob("*.jsonl")) if archived.exists() else 0
    executable = shutil.which("codex")
    if executable and not (os.name == "nt" and "windowsapps" in executable.lower()):
        appserver = DataSourceStatus("Codex app-server", executable, "ok")
    elif executable:
        appserver = DataSourceStatus("Codex app-server", "检测到 WindowsApps 执行别名，将使用 session 额度回退", "warning")
    else:
        appserver = DataSourceStatus("Codex app-server", "未找到 CLI，将使用 session 额度回退", "warning")
    claude = home / ".claude" / "projects"
    return [
        appserver,
        DataSourceStatus("Codex SQLite", str(state) if state.exists() else "state_5.sqlite 不存在", "ok" if state.exists() else "error"),
        DataSourceStatus("Codex 精细事件", f"{session_count} session · {archived_count} archived", "ok" if session_count + archived_count else "error"),
        DataSourceStatus("Claude Code", str(claude) if claude.exists() else "未启用或暂无 transcript", "ok" if claude.exists() else "warning"),
    ]
