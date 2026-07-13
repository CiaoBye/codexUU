from pathlib import Path


APP_NAME = "CodexUU"
VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()
APP_REPO = "CiaoBye/codexUU"


def next_version(version: str) -> str:
    """按每段 10 轮进位：0.0.10 -> 0.1.01。"""
    major_text, minor_text, patch_text = str(version).split(".")
    major, minor, patch = int(major_text), int(minor_text), int(patch_text)
    if patch >= 10:
        return f"{major}.{minor + 1}.01"
    width = 2 if minor > 0 or len(patch_text) > 1 else 1
    return f"{major}.{minor}.{patch + 1:0{width}d}"
