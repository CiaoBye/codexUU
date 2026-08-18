from pathlib import Path


def test_windows_release_is_manual_only():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "publish_release:" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "dist/installer/*.sha256" in workflow
    assert "push:\n" not in workflow
