from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.utils.statistics_timezone import get_statistics_timezone


_RESOURCES_ROOT = Path(__file__).resolve().parents[2] / "Resources" / "Palettes"
_MISSING = object()


def _read_token_value(current: Any, part: str):
    if isinstance(current, dict):
        return current.get(part, _MISSING)
    if isinstance(current, (list, tuple)):
        if not part.isdigit():
            return _MISSING
        index = int(part)
        return current[index] if index < len(current) else _MISSING
    if is_dataclass(current):
        names = {item.name for item in fields(current)}
        field_name = part if part in names else re.sub(r"(?<!^)(?=[A-Z])", "_", part).lower()
        return getattr(current, field_name, _MISSING) if field_name in names else _MISSING
    return _MISSING


@dataclass
class PaletteTokens:
    palette_id: str
    appearance: str
    accent: Dict = field(default_factory=dict)
    quota: Dict = field(default_factory=dict)
    data: Dict = field(default_factory=dict)
    selection: Dict = field(default_factory=dict)
    surface_tint: Dict = field(default_factory=dict)
    ornament: Dict = field(default_factory=dict)

    def get(self, path: str, fallback=None):
        current = self
        for part in path.split("."):
            current = _read_token_value(current, part)
            if current is _MISSING:
                return fallback
        return fallback if current is None else current


@dataclass
class PaletteDefinition:
    palette_id: str
    version: str
    lifecycle: str
    default_locale: str
    localizations: Dict[str, str]
    variants: Dict[str, str]
    asset_manifest: str
    author: Dict
    license: str
    capabilities: list[str]
    source: Dict
    resource_root: Path = field(default=_RESOURCES_ROOT, repr=False, compare=False)

    def resolve_appearance(self, appearance: str) -> str:
        if appearance in self.variants:
            return appearance
        if "dark" in self.variants:
            return "dark"
        return next(iter(self.variants), appearance)

    def token_path(self, appearance: str) -> Path:
        variant = self.variants.get(self.resolve_appearance(appearance))
        return self.resource_root / self.palette_id / variant

    def load_tokens(self, appearance: str) -> PaletteTokens:
        actual_appearance = self.resolve_appearance(appearance)
        path = self.token_path(actual_appearance)
        data = json.loads(path.read_text(encoding="utf-8"))
        return PaletteTokens(
            palette_id=self.palette_id,
            appearance=actual_appearance,
            accent=data.get("accent", {}),
            quota=data.get("quota", {}),
            data=data.get("data", {}),
            selection=data.get("selection", {}),
            surface_tint=data.get("surfaceTint", {}),
            ornament=data.get("ornament", {}),
        )

    def localized_name(self, locale: str = "zh-Hans") -> str:
        for candidate in (locale, self.default_locale, "en"):
            reference = self.localizations.get(candidate)
            if not isinstance(reference, str) or not reference.strip():
                continue
            path = self.resource_root / self.palette_id / reference
            if path.is_file():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                name = data.get("displayName") if isinstance(data, dict) else None
                if isinstance(name, str) and name.strip():
                    return name.strip()
            elif not reference.lower().endswith(".json"):
                return reference.strip()
        return self.palette_id


class PaletteManager:
    def __init__(self, root: Optional[Path] = None):
        self._root = root or _RESOURCES_ROOT
        self._palettes: Dict[str, PaletteDefinition] = {}
        self._current_tokens: Optional[PaletteTokens] = None
        self._current_appearance: str = "dark"
        self._load_palettes()

    @property
    def palette_ids(self) -> list[str]:
        return sorted(self._palettes.keys())

    def get(self, palette_id: str) -> Optional[PaletteDefinition]:
        return self._palettes.get(palette_id)

    def load_tokens(self, palette_id: str, appearance: str) -> Optional[PaletteTokens]:
        palette = self.get(palette_id)
        if not palette:
            return None
        try:
            return palette.load_tokens(appearance)
        except (OSError, TypeError, json.JSONDecodeError):
            return None

    @property
    def current_tokens(self) -> PaletteTokens:
        return self._current_tokens or PaletteTokens(
            palette_id="",
            appearance="dark",
            accent={},
            quota={},
            data={},
            selection={},
            surface_tint={},
            ornament={},
        )

    @property
    def current_appearance(self) -> str:
        return getattr(self, "_current_appearance", "dark")

    def load(self, palette_id: str, appearance: Optional[str] = None) -> bool:
        palette = self.get(palette_id)
        if not palette:
            return False
        preferred = appearance if appearance in ("light", "dark") else self.current_appearance
        appearances = [preferred, "light" if preferred == "dark" else "dark"]
        for variant in appearances:
            if variant not in palette.variants:
                continue
            tokens = self.load_tokens(palette_id, variant)
            if tokens:
                self._current_tokens = tokens
                self._current_appearance = tokens.appearance
                return True
        return False

    def _load_palettes(self):
        if not self._root.exists():
            return
        for path in self._root.iterdir():
            if not path.is_dir():
                continue
            manifest = path / "manifest.json"
            if not manifest.exists():
                continue
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            self._palettes[data.get("id", path.name)] = PaletteDefinition(
                palette_id=data.get("id", path.name),
                version=str(data.get("version", "1.0.0")),
                lifecycle=str(data.get("lifecycle", "stable")),
                default_locale=str(data.get("defaultLocale", "zh-Hans")),
                localizations=data.get("localizations", {}),
                variants=data.get("variants", {"dark": "tokens/dark.json", "light": "tokens/light.json"}),
                asset_manifest=str(data.get("assetManifest", "")),
                author=data.get("author", {}),
                license=str(data.get("license", "MIT")),
                capabilities=list(data.get("capabilities", [])),
                source=data.get("source", {}),
                resource_root=self._root,
            )
