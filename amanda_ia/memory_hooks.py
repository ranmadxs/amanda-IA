"""Hook global para eventos de storage/memoria.

Módulo liviano sin imports de amanda_ia para evitar circulares.
Cualquier módulo que escribe/lee storage llama emit().
agent.py lo conecta a phase["memory_log"] al inicio de process().
"""
from __future__ import annotations
from typing import Callable

_on_memory: Callable[[str, str], None] | None = None


def set_hook(fn: Callable[[str, str], None] | None) -> None:
    global _on_memory
    _on_memory = fn


def emit(op: str, detail: str) -> None:
    if _on_memory:
        try:
            _on_memory(op, detail)
        except Exception:
            pass
