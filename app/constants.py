from pathlib import Path


APP_NAME = "CodexUU"
VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()
APP_REPO = "CiaoBye/codexUU"
