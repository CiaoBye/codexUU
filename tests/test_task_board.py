from datetime import datetime, timezone

from app.data.models import RuntimeScope, TaskItem
from app.ui.task_board import aggregate_tasks_by_project


def test_tasks_are_aggregated_by_project_and_active_status_wins():
    now = datetime.now(timezone.utc)
    tasks = [
        TaskItem("a", "已归档对话", "completed", RuntimeScope.CODEX, now, "CodexUU"),
        TaskItem("b", "当前开发对话", "running", RuntimeScope.CODEX, now, "CodexUU"),
        TaskItem("c", "其他项目完成", "completed", RuntimeScope.CODEX, now, "Other"),
    ]
    projects = aggregate_tasks_by_project(tasks)
    assert [(item.title, item.status, item.thread_count) for item in projects] == [
        ("CodexUU", "running", 2),
        ("Other", "completed", 1),
    ]
