import json

from app.utils import update_checker


class _Response:
    status_code = 200
    headers = {"ETag": '"test"'}

    def json(self):
        return [
            {"tag_name": "v1.1.0-beta", "html_url": "beta", "prerelease": True},
            {"tag_name": "v1.0.4", "html_url": "stable", "prerelease": False, "assets": [
                {"name": "CodexUU-windows-x64.zip", "browser_download_url": "download"},
            ]},
        ]


def test_update_checker_selects_stable_and_caches_negative_result(tmp_path, monkeypatch):
    monkeypatch.setattr(update_checker, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(update_checker, "CACHE_FILE", tmp_path / "update.json")
    monkeypatch.setattr(update_checker.requests, "get", lambda *args, **kwargs: _Response())

    release = update_checker.check_for_update("v1.0.3", include_beta=False, force=True)
    assert release is not None
    assert release.tag_name == "v1.0.4"
    assert release.download_url == "download"
    assert json.loads((tmp_path / "update.json").read_text())["etag"] == '"test"'

    assert update_checker.check_for_update("v1.0.4", include_beta=False, force=True) is None
    cached = json.loads((tmp_path / "update.json").read_text())
    assert cached["release"] is None
