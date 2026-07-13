from pathlib import Path

from packaging.version import Version

from app.constants import APP_VERSION


def test_version_file_matches_runtime_constant():
    root = Path(__file__).resolve().parents[1]
    version_file = root / "VERSION"
    assert version_file.read_text(encoding="utf-8").strip() == APP_VERSION
    assert Version(APP_VERSION) >= Version("0.0.1")
    assert APP_VERSION in (root / "README.md").read_text(encoding="utf-8")
    assert f"· {APP_VERSION} ·" in (root / "agents" / "changelog.md").read_text(encoding="utf-8")
