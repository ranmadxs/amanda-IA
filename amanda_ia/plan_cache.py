"""Cache de planificación: memoria + disco en .aia/cache/."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from amanda_ia.config import _project_root, _load_json


def _cache_path() -> Path:
    return _project_root() / ".aia" / "cache" / "planner.json"


def _get_ttl_hours() -> float:
    project = _project_root()
    settings_path = project / ".aia" / "settings.json"
    data = _load_json(settings_path)
    cfg = data.get("classifierCache", {})
    if isinstance(cfg, dict):
        return float(cfg.get("ttlHours", 6))
    return 6.0


def _prompt_key(prompt: str) -> str:
    return hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()


_memory_cache: dict[str, tuple[str, float]] = {}


def _load_disk_cache() -> dict:
    path = _cache_path()
    if not path.exists():
        return {}
    data = _load_json(path)
    return data.get("entries", {}) if isinstance(data, dict) else {}


def _save_disk_cache(entries: dict) -> None:
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "entries": entries}, f, indent=2, ensure_ascii=False)


def get(prompt: str) -> str | None:
    key = _prompt_key(prompt)
    ttl_sec = _get_ttl_hours() * 3600
    now = time.time()

    if key in _memory_cache:
        plan, ts = _memory_cache[key]
        if now - ts < ttl_sec:
            return plan
        del _memory_cache[key]

    disk = _load_disk_cache()
    if key in disk:
        entry = disk[key]
        ts = entry.get("timestamp", 0)
        if now - ts < ttl_sec:
            plan = entry.get("plan", "")
            _memory_cache[key] = (plan, ts)
            return plan

    return None


def set_(prompt: str, plan: str) -> None:
    key = _prompt_key(prompt)
    now = time.time()
    _memory_cache[key] = (plan, now)
    disk = _load_disk_cache()
    disk[key] = {"plan": plan, "timestamp": now}
    _save_disk_cache(disk)


def delete_all() -> None:
    global _memory_cache
    _memory_cache.clear()
    path = _cache_path()
    if path.exists():
        path.unlink()
