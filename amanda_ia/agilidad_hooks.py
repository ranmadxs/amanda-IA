"""Filtro global de rutinas para phase["agilidad"].

Dos mecanismos:
1. emit() explícito: cualquier módulo puede llamarlo directamente.
2. AgilidadHandler: logging.Handler que intercepta todos los loggers de
   amanda_ia.* y reenvía al hook — captura rutinas automáticamente.

Uso en agent.py:
    from amanda_ia.agilidad_hooks import set_hook, AgilidadHandler, emit as _agil_emit
    # al inicio de process():
    _set_hook(lambda op, d: phase.setdefault("agilidad", []).append(f"{op}>> {d}"))
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

_on_agilidad: Callable[[str, str], None] | None = None
_handler: "AgilidadHandler | None" = None
_lock = threading.Lock()


def set_hook(fn: Callable[[str, str], None] | None) -> None:
    global _on_agilidad
    _on_agilidad = fn


def emit(op: str, detail: str = "") -> None:
    if _on_agilidad:
        try:
            _on_agilidad(op, detail)
        except Exception:
            pass


# ── Logging handler global ────────────────────────────────────────────────────

# Patrones que indican inicio de una rutina relevante (busca en el mensaje formateado)
_ROUTINE_PATTERNS: list[tuple[str, str]] = [
    # (fragmento en el mensaje, etiqueta op)
    ("ROUTINE:",    "ROUTINE"),
    ("ollama_chat", "LLM_CALL"),
    ("tool_calls",  "TOOL_CALLS"),
    ("process(",    "PROCESS"),
    ("_plan_exec",  "PLAN_EXEC"),
    ("compress",    "COMPRESS"),
    ("classify",    "CLASSIFY"),
]


class AgilidadHandler(logging.Handler):
    """Handler que intercepta loggers amanda_ia.* y emite eventos ROUTINE."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)

    def emit(self, record: logging.LogRecord) -> None:
        if not _on_agilidad:
            return
        msg = record.getMessage()
        for frag, op in _ROUTINE_PATTERNS:
            if frag.lower() in msg.lower():
                try:
                    _on_agilidad(op, f"{record.name.split('.')[-1]}: {msg[:120]}")
                except Exception:
                    pass
                return


def install(phase: dict) -> AgilidadHandler:
    """Instala el handler global en el logger raíz de amanda_ia y conecta el hook."""
    global _handler
    set_hook(lambda op, d: phase.setdefault("agilidad", []).append(f"{op}>> {d}"))
    root = logging.getLogger("amanda_ia")
    # Evitar duplicados si ya está instalado
    for h in root.handlers:
        if isinstance(h, AgilidadHandler):
            return h
    h = AgilidadHandler()
    root.addHandler(h)
    _handler = h
    return h


def uninstall() -> None:
    """Quita el handler del logger raíz."""
    global _handler
    root = logging.getLogger("amanda_ia")
    for h in list(root.handlers):
        if isinstance(h, AgilidadHandler):
            root.removeHandler(h)
    _handler = None
    set_hook(None)
