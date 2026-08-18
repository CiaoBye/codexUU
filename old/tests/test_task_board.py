from datetime import datetime, timezone

from app.data.models import RuntimeScope, TaskItem
from app.ui.task_board import aggregate_tasks_by_project


def test_archived_threads_are_grouped_as_project_history_entries():
    now = datetime.now(timezone.utc)
    tasks = [
        TaskItem("a", "已归档对话", "completed", RuntimeScope.CODEX, now, "CodexUU"),
        TaskItem("a2", "另一条已归档对话", "completed", RuntimeScope.CODEX, now, "CodexUU"),
        TaskItem("b", "当前开发对话", "running", RuntimeScope.CODEX, now, "CodexUU"),
        TaskItem("c", "其他项目完成", "completed", RuntimeScope.CODEX, now, "Other"),
    ]
    projects = aggregate_tasks_by_project(tasks)
    assert [(item.title, item.status, item.thread_count) for item in projects] == [
        ("CodexUU", "running", 1),
        ("CodexUU", "completed", 2),
        ("Other", "completed", 1),
    ]
