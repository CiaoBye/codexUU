from __future__ import annotations

from dataclasses import dataclass, field

from app.data.models import MultiRuntimeUsageSnapshot, RuntimeScope


@dataclass
class DashboardViewModel:
    """Qt-free state boundary between dashboard data and presentation widgets."""

    data: MultiRuntimeUsageSnapshot = field(default_factory=MultiRuntimeUsageSnapshot)
    runtime_scope: RuntimeScope = RuntimeScope.CODEX
    model_scope: str = "all"

    def set_records(self, codex, tasks, daily_tokens, projects, tools, skills, models, ccswitch):
        self.data = MultiRuntimeUsageSnapshot(
            codex=codex,
            ccswitch=ccswitch,
            tasks=list(tasks or []),
            daily_tokens=sorted(list(daily_tokens or []), key=lambda item: item.date, reverse=True),
            projects=sorted(list(projects or []), key=lambda item: item.token_total, reverse=True),
            tools=list(tools or []),
            skills=list(skills or []),
            models=list(models or []),
        )

    def provider_snapshot(self):
        snapshot = self.data.ccswitch
        return snapshot if snapshot is not None and snapshot.provider_name else None

    def visible_data(self):
        scope = self.runtime_scope
        return (
            [item for item in self.data.tasks if item.runtime == scope],
            [item for item in self.data.daily_tokens if item.runtime == scope],
            [item for item in self.data.projects if item.runtime == scope],
            [item for item in self.data.tools if item.runtime == scope],
            [item for item in self.data.skills if item.runtime == scope],
        )

    def visible_models(self):
        return [item for item in self.data.models if item.runtime == self.runtime_scope]
