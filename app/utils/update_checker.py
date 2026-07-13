from __future__ import annotations
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from packaging.version import Version

APP_REPO = "shanggqm/codexU"
GITHUB_API = f"https://api.github.com/repos/{APP_REPO}/releases/latest"
CACHE_DIR = Path(os.path.expanduser("~")) / "Library" / "Caches" / "codexU" / "win"
CACHE_FILE = CACHE_DIR / "update-check.json"


class GitHubRelease:
    def __init__(self, tag_name: str, html_url: str, body: str, published_at: str):
        self.tag_name = tag_name
        self.html_url = html_url
        self.body = body
        self.published_at = published_at

    @property
    def version(self) -> Optional[Version]:
        try:
            v = self.tag_name.lstrip("v")
            return Version(v)
        except Exception:
            return None


def check_for_update(
    current_version: str,
    include_beta: bool = True,
    force: bool = False,
) -> Optional[GitHubRelease]:
    now = time.time()

    if not force:
        cached = _read_cache()
        if cached:
            elapsed = now - cached.get("checked_at", 0)
            if elapsed < 86400:
                release_data = cached.get("release")
                if release_data:
                    return GitHubRelease(
                        tag_name=release_data["tag_name"],
                        html_url=release_data["html_url"],
                        body=release_data.get("body", ""),
                        published_at=release_data.get("published_at", ""),
                    )

    try:
        resp = requests.get(GITHUB_API, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        tag = data.get("tag_name", "")
        html_url = data.get("html_url", "")
        body = data.get("body", "")
        published = data.get("published_at", "")

        release = GitHubRelease(tag, html_url, body, published)

        if not include_beta:
            if "beta" in tag.lower() or "alpha" in tag.lower() or "rc" in tag.lower():
                return None

        current = _parse_version(current_version)
        latest = release.version
        if latest and current and latest > current:
            _write_cache(release)
            return release

        return None

    except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
        return None


def _parse_version(version_str: str) -> Optional[Version]:
    try:
        return Version(version_str.lstrip("v"))
    except Exception:
        return None


def _read_cache() -> Optional[dict]:
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_cache(release: GitHubRelease):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "checked_at": time.time(),
                "release": {
                    "tag_name": release.tag_name,
                    "html_url": release.html_url,
                    "body": release.body,
                    "published_at": release.published_at,
                },
            }, f)
    except OSError:
        pass
