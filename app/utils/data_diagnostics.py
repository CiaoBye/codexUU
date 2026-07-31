from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.data.codex_reader import _appserver_executables, get_appserver_diagnostics

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
    executables = _appserver_executables()
    runtime = get_appserver_diagnostics()
    runtime_labels = {
        "unavailable": "未启动",
        "starting": "初始化中",
        "ready": "已就绪",
        "timeout": "响应超时",
        "disconnected": "已断开",
        "exited": "进程已退出",
    }
    runtime_state = runtime_labels.get(runtime.get("status"), "未知状态")
    runtime_error = runtime.get("last_error")
    if executables:
        detail = f"实时优先：{executables[0]}；通道：{runtime_state}"
        if runtime_error:
            detail += f"；最近错误：{runtime_error}"
        appserver = DataSourceStatus(
            "Codex app-server", detail, "ok" if runtime.get("status") == "ready" else "warning",
        )
    else:
        appserver = DataSourceStatus("Codex app-server", "未找到可执行独立 runtime；额度使用最新 session rate-limit 快照", "warning")
    return [
        appserver,
        DataSourceStatus("Codex SQLite", str(state) if state.exists() else "state_5.sqlite 不存在", "ok" if state.exists() else "error"),
        DataSourceStatus("Codex 精细事件", f"{session_count} session · {archived_count} archived", "ok" if session_count + archived_count else "error"),
    ]
