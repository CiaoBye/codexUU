from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.data.local_index import local_index_status


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
    state_candidates = (codex / "state_5.sqlite", codex / "sqlite" / "state_5.sqlite")
    state = next((path for path in state_candidates if path.exists()), state_candidates[0])
    session_count = sum(1 for _ in sessions.rglob("*.jsonl")) if sessions.exists() else 0
    archived_count = sum(1 for _ in archived.glob("*.jsonl")) if archived.exists() else 0
    executable = shutil.which("codex")
    if executable and not (os.name == "nt" and "windowsapps" in executable.lower()):
        appserver = DataSourceStatus("Codex app-server", f"实时优先：{executable}", "ok")
    elif executable:
        appserver = DataSourceStatus("Codex app-server", "Windows 桌面版受系统启动限制；额度使用最新 session rate-limit 快照", "warning")
    else:
        appserver = DataSourceStatus("Codex app-server", "未找到独立 CLI；额度使用最新 session rate-limit 快照", "warning")
    claude = home / ".claude" / "projects"
    index = local_index_status()
    if index.available:
        scan_time = index.last_scan.astimezone().strftime("%m/%d %H:%M") if index.last_scan else "等待首次扫描"
        index_detail = f"{index.file_count} 文件 · {index.event_count} 条派生事件 · {scan_time}"
        index_status = DataSourceStatus("CodexUU 本机索引", index_detail, "ok")
    else:
        index_status = DataSourceStatus("CodexUU 本机索引", "首次读取 Claude transcript 时创建；不保存对话正文", "warning")
    return [
        appserver,
        DataSourceStatus("Codex SQLite", str(state) if state.exists() else "state_5.sqlite 不存在", "ok" if state.exists() else "error"),
        DataSourceStatus("Codex 精细事件", f"{session_count} session · {archived_count} archived", "ok" if session_count + archived_count else "error"),
        DataSourceStatus("Claude Code", str(claude) if claude.exists() else "未启用或暂无 transcript", "ok" if claude.exists() else "warning"),
        index_status,
    ]
