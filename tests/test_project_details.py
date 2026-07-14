from datetime import datetime, timezone

from app.data.models import ModelUsage, ProjectStats, RuntimeScope, SessionUsage
from app.ui.project_details import project_export_payload, project_markdown


def test_project_export_uses_selected_period_and_keeps_model_session_breakdown():
    project = ProjectStats(
        name="demo",
        token_total=900,
        estimated_value=1.8,
        thread_count=3,
        runtime=RuntimeScope.CODEX,
        current_week_token_total=240,
        current_week_estimated_value=0.48,
        current_week_pricing_coverage_pct=100.0,
        model_usage=[ModelUsage("gpt-5", 900, 1.8, 100.0)],
        sessions=[SessionUsage("abc123", 600, datetime(2026, 7, 14, tzinfo=timezone.utc), "gpt-5")],
    )

    payload = project_export_payload(project, "week")

    assert payload["period"] == "week"
    assert payload["token_total"] == 240
    assert payload["models"][0]["name"] == "gpt-5"
    assert payload["sessions"][0]["session_id"] == "abc123"
    assert "模型拆分" in project_markdown(payload)
