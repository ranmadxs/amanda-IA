"""Persistencia de historial de conversación por modo.

Cada modo guarda sus conversaciones en .aia/history/{mode}/
Formato: YYYYMMDD_HHMMSS.json
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from amanda_ia.config import _project_root
from amanda_ia.memory_hooks import emit as _mem_emit

_MAX_PER_MODE = 30  # máximo de conversaciones guardadas por modo


def _history_dir(mode: str) -> Path:
    key = mode if mode else "aia"
    return _project_root() / ".aia" / "history" / key


def _title_from_history(messages: list[dict]) -> str:
    """Extrae el primer mensaje del usuario como título."""
    for m in messages:
        if m.get("role") == "user":
            text = m.get("content", "").strip()
            return text[:60] + ("…" if len(text) > 60 else "")
    return "Conversación"


def save(mode: str, messages: list[dict]) -> None:
    """Guarda el historial actual en disco. Solo si hay al menos un intercambio."""
    if not messages or len(messages) < 2:
        return
    d = _history_dir(mode)
    d.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    entry = {
        "id": ts,
        "mode": mode or "aia",
        "date": datetime.now().isoformat(timespec="seconds"),
        "title": _title_from_history(messages),
        "messages": messages,
    }
    (d / f"{ts}.json").write_text(
        json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _prune(d)
    _mem_emit("HISTORY_SAVE", f"mode={mode or 'aia'} msgs={len(messages)} id={ts}")


def _prune(d: Path) -> None:
    """Elimina archivos más antiguos si supera el límite."""
    files = sorted(d.glob("*.json"))
    for old in files[:-_MAX_PER_MODE]:
        old.unlink(missing_ok=True)


def list_all(mode: str) -> list[dict]:
    """Lista conversaciones guardadas para el modo, más recientes primero."""
    d = _history_dir(mode)
    if not d.exists():
        return []
    entries = []
    for f in sorted(d.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            entries.append({
                "id": data.get("id", f.stem),
                "date": data.get("date", ""),
                "title": data.get("title", "Conversación"),
                "turns": sum(1 for m in data.get("messages", []) if m.get("role") == "user"),
            })
        except Exception:
            pass
    return entries


def load(mode: str, hid: str) -> list[dict] | None:
    """Carga los mensajes de una conversación por ID. None si no existe."""
    d = _history_dir(mode)
    path = d / f"{hid}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except Exception:
        return None


def delete(mode: str, hid: str) -> bool:
    """Elimina una conversación. True si se borró."""
    path = _history_dir(mode) / f"{hid}.json"
    if path.exists():
        path.unlink()
        return True
    return False
