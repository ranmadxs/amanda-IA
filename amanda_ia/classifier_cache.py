"""Cache de clasificación: memoria + disco en .aia/cache/."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from amanda_ia.config import _project_root, _load_json


def _cache_path() -> Path:
    return _project_root() / ".aia" / "cache" / "classifier.json"


def _get_ttl_hours() -> float:
    """TTL en horas desde .aia/settings.json."""
    project = _project_root()
    settings_path = project / ".aia" / "settings.json"
    data = _load_json(settings_path)
    cfg = data.get("classifierCache", {})
    if isinstance(cfg, dict):
        return float(cfg.get("ttlHours", 6))
    return 6.0


def _prompt_key(prompt: str) -> str:
    """Hash del prompt para usar como clave."""
    normalized = prompt.strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# Cache en memoria (se borra al cerrar)
_memory_cache: dict[str, tuple[list[str], float]] = {}


def _load_disk_cache() -> dict[str, dict[str, Any]]:
    path = _cache_path()
    if not path.exists():
        return {}
    data = _load_json(path)
    return data.get("entries", {}) if isinstance(data, dict) else {}


def _save_disk_cache(entries: dict[str, dict[str, Any]]) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "entries": entries}, f, indent=2, ensure_ascii=False)


def get(prompt: str) -> list[str] | None:
    """
    Obtiene la clasificación cacheada. None si no existe o expiró.
    """
    key = _prompt_key(prompt)
    ttl_sec = _get_ttl_hours() * 3600
    now = time.time()

    # Memoria primero
    if key in _memory_cache:
        selected, ts = _memory_cache[key]
        if now - ts < ttl_sec:
            return selected
        del _memory_cache[key]

    # Disco
    disk = _load_disk_cache()
    if key in disk:
        entry = disk[key]
        ts = entry.get("timestamp", 0)
        if now - ts < ttl_sec:
            selected = entry.get("selected", [])
            _memory_cache[key] = (selected, ts)
            return selected

    return None


def set_(prompt: str, selected: list[str]) -> None:
    """Guarda la clasificación en memoria y disco."""
    key = _prompt_key(prompt)
    now = time.time()
    _memory_cache[key] = (selected, now)

    disk = _load_disk_cache()
    disk[key] = {"selected": selected, "timestamp": now}
    _save_disk_cache(disk)


def delete_all() -> None:
    """Borra toda la cache (memoria + disco)."""
    global _memory_cache
    _memory_cache.clear()
    path = _cache_path()
    if path.exists():
        path.unlink()
