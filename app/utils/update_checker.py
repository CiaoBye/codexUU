from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import requests
from packaging.version import Version
from app.constants import APP_REPO, APP_VERSION


GITHUB_API = f"https://api.github.com/repos/{APP_REPO}/releases?per_page=20"
if os.name == "nt":
    _cache_root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
else:
    _cache_root = Path(os.path.expanduser("~")) / "Library" / "Caches"
CACHE_DIR = _cache_root / "codexU" / "updates"
CACHE_FILE = CACHE_DIR / "update-check.json"
CACHE_TTL = 86400


class GitHubRelease:
    def __init__(self, tag_name: str, html_url: str, body: str, published_at: str,
                 prerelease: bool = False, download_url: str = ""):
        self.tag_name = tag_name
        self.html_url = html_url
        self.body = body
        self.published_at = published_at
        self.prerelease = prerelease
        self.download_url = download_url

    @property
    def version(self) -> Optional[Version]:
        return _parse_version(self.tag_name)

    def to_dict(self) -> dict:
        return {
            "tag_name": self.tag_name,
            "html_url": self.html_url,
            "body": self.body,
            "published_at": self.published_at,
            "prerelease": self.prerelease,
            "download_url": self.download_url,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GitHubRelease":
        return cls(
            tag_name=str(data.get("tag_name", "")),
            html_url=str(data.get("html_url", "")),
            body=str(data.get("body", "") or ""),
            published_at=str(data.get("published_at", "") or ""),
            prerelease=bool(data.get("prerelease", False)),
            download_url=str(data.get("download_url", "") or ""),
        )


def check_for_update(current_version: str, include_beta: bool = True, force: bool = False) -> Optional[GitHubRelease]:
    now = time.time()
    cached = _read_cache()
    cache_key_matches = cached and (
        cached.get("current_version") == current_version
        and bool(cached.get("include_beta", True)) == bool(include_beta)
    )
    if not force and cache_key_matches and now - float(cached.get("checked_at", 0)) < CACHE_TTL:
        release_data = cached.get("release")
        return GitHubRelease.from_dict(release_data) if isinstance(release_data, dict) else None

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"CodexUU/{APP_VERSION}",
    }
    if cached and cached.get("etag"):
        headers["If-None-Match"] = str(cached["etag"])
    try:
        response = requests.get(GITHUB_API, headers=headers, timeout=10)
        if response.status_code == 304 and cached:
            cached["checked_at"] = now
            _write_cache_data(cached)
            release_data = cached.get("release")
            return GitHubRelease.from_dict(release_data) if isinstance(release_data, dict) else None
        if response.status_code != 200:
            return None
        releases = response.json()
        if not isinstance(releases, list):
            return None
        release = _select_release(releases, include_beta)
        current = _parse_version(current_version)
        if release and current and release.version and release.version <= current:
            release = None
        _write_cache_data({
            "checked_at": now,
            "current_version": current_version,
            "include_beta": bool(include_beta),
            "etag": response.headers.get("ETag", ""),
            "release": release.to_dict() if release else None,
        })
        return release
    except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError):
        return None


def _select_release(items: list[dict], include_beta: bool) -> Optional[GitHubRelease]:
    candidates = []
    for item in items:
        if not isinstance(item, dict) or item.get("draft"):
            continue
        tag = str(item.get("tag_name", ""))
        if not tag or _parse_version(tag) is None:
            continue
        prerelease = bool(item.get("prerelease", False)) or any(
            marker in tag.lower() for marker in ("alpha", "beta", "rc")
        )
        if prerelease and not include_beta:
            continue
        assets = item.get("assets") if isinstance(item.get("assets"), list) else []
        downloadable = [
            asset for asset in assets if isinstance(asset, dict)
            and str(asset.get("name", "")).lower().endswith((".msi", ".exe", ".zip"))
        ]
        preferred = next((asset for asset in downloadable if "win" in str(asset.get("name", "")).lower()), None)
        preferred = preferred or (downloadable[0] if downloadable else None)
        candidates.append(GitHubRelease(
            tag_name=tag,
            html_url=str(item.get("html_url", "")),
            body=str(item.get("body", "") or ""),
            published_at=str(item.get("published_at", "") or ""),
            prerelease=prerelease,
            download_url=str(preferred.get("browser_download_url", "")) if preferred else "",
        ))
    candidates.sort(key=lambda release: release.version or Version("0"), reverse=True)
    return candidates[0] if candidates else None


def _parse_version(version_str: str) -> Optional[Version]:
    try:
        return Version(str(version_str).lstrip("v"))
    except Exception:
        return None


def _read_cache() -> Optional[dict]:
    try:
        if CACHE_FILE.exists():
            with CACHE_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return None


def _write_cache_data(data: dict):
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with CACHE_FILE.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass
