"""Monitor en vivo: cliente SSE del servidor monitor MCP."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from typing import Callable

MONITOR_SSE_URL = "http://localhost:8003/live"

_active = False
_client = None  # httpx.Client cuando está activo


def is_active() -> bool:
    return _active


def stop() -> None:
    global _active, _client
    _active = False
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def start(
    append_cb: Callable[[str], None],
    app_invalidate: Callable[[], None],
    loop,
) -> str | None:
    """Conecta al SSE del servidor monitor y llama append_cb con cada lectura.

    Retorna None si inicia el thread (el server puede aún no estar disponible).
    Los errores de conexión se reportan via append_cb en el TUI.
    """
    global _active, _client

    try:
        import httpx
    except ImportError:
        return "httpx no instalado. Ejecuta: poetry add httpx"

    _client = httpx.Client()
    _active = True

    def _notify(msg: str) -> None:
        def _do():
            append_cb(msg)
            app_invalidate()
        loop.call_soon_threadsafe(_do)

    def _thread() -> None:
        import httpx as _httpx

        timeout = _httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0)
        first_attempt = True

        while _active:
            try:
                with _client.stream(
                    "GET",
                    MONITOR_SSE_URL,
                    headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
                    timeout=timeout,
                ) as resp:
                    if resp.status_code != 200:
                        _notify(
                            f"Error al conectar al monitor: HTTP {resp.status_code}\n"
                            "Asegurate de que el servidor MCP monitor está corriendo "
                            "con el endpoint /live (reinicia: poetry run mcp monitor --http)\n"
                        )
                        stop()
                        return

                    if first_attempt:
                        first_attempt = False
                        _notify("Conectado al stream MQTT. Esperando datos...\n")

                    for raw_line in resp.iter_lines():
                        if not _active:
                            break
                        if not raw_line.startswith("data: "):
                            continue
                        try:
                            data = json.loads(raw_line[6:])
                            litros = float(data.get("litros") or 0)
                            pct = float(data.get("porcentaje") or 0)
                            dist = float(data.get("distancia") or 0)
                            estado = data.get("estado", "?")
                            ts = datetime.now().strftime("%H:%M:%S")
                            line = f"[{ts}]  {litros:.0f} L  {pct:.1f}%  dist {dist:.1f} cm  {estado}\n"

                            def _update(l: str = line) -> None:
                                append_cb(l)
                                app_invalidate()

                            loop.call_soon_threadsafe(_update)
                        except Exception:
                            pass

            except Exception as exc:
                if not _active:
                    break
                if first_attempt:
                    first_attempt = False
                    _notify(
                        f"No se pudo conectar al monitor ({exc})\n"
                        "Reinicia el servidor: poetry run mcp monitor --http\n"
                    )
                    stop()
                    return
                # Reconexión silenciosa en subsiguientes intentos
                time.sleep(3)

    threading.Thread(target=_thread, daemon=True).start()
    return None
