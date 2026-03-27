"""Servidor web chatbot para amanda-IA.

Uso:
    aia --web           # puerto 8080
    aia --web --port 3000
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import datetime
from pathlib import Path

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

import amanda_ia.agent as agent_mod
from amanda_ia.agent import process
from amanda_ia.config import get_mods, get_mods_raw

RESOURCES = Path(__file__).resolve().parent / "resources"
STATIC = Path(__file__).resolve().parent / "static"

MONITOR_SSE_URL = "http://localhost:8003/live"

# Procesa una petición a la vez (herramienta personal)
_lock = threading.Lock()
# Modo activo en la sesión web (None = modo general AiA)
_web_mode: str | None = None

_RICH_RE = re.compile(r"\[/?[^\]]*\]")
_IMG_RE = re.compile(r"\[AIA_IMG:[^\]]+\]")

# Comandos TUI-only que tienen implementación propia en web (no bloquear, manejar)
_WEB_HANDLED = {"/watch"}


def _strip(text: str) -> str:
    text = _IMG_RE.sub("", text)
    return _RICH_RE.sub("", text).strip()


def _load_banner(banner_name: str) -> str:
    path = RESOURCES / f"{banner_name}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _all_mods_info() -> list[dict]:
    result = [{
        "name": "aia",
        "key": "",
        "displayName": "AiA",
        "banner": _load_banner("banner"),
        "color": "#7f8c8d",
        "colorDim": "#2c3e50",
    }]
    for m in get_mods():
        result.append({
            "name": m.get("name"),
            "key": m.get("key", ""),
            "displayName": m.get("name", "").capitalize(),
            "banner": _load_banner(m.get("banner", "banner")),
            "color": m.get("color", "#7f8c8d"),
            "colorDim": m.get("colorDim", "#2c3e50"),
        })
    return result


def _web_commands(mode_key: str | None) -> list[dict]:
    """Comandos slash disponibles para el modo actual en la web."""
    cmds: list[dict] = []
    cmds.append({"cmd": "/help",          "desc": "Listar herramientas disponibles del modo actual"})
    cmds.append({"cmd": "/mcp list",      "desc": "Listar servidores MCP activos"})
    cmds.append({"cmd": "/mod list",      "desc": "Listar modos disponibles"})
    cmds.append({"cmd": "/cache delete",  "desc": "Borrar caché (clasificador, MCP, historial)"})
    cmds.append({"cmd": "/flush history", "desc": "Limpiar historial de conversación"})
    cmds.append({"cmd": "/flush all",     "desc": "Limpiar todo (caché + historial + Ollama)"})

    if mode_key:
        mods = get_mods_raw()
        mod = next((m for m in mods if m.get("key") == mode_key), None)
        if mod:
            mod_cmds = mod.get("commands", {})
            for cmd_name in mod.get("slashCommands", []):
                if cmd_name == "/watch":
                    cmds.append({"cmd": "/watch", "desc": "Monitor en vivo (SSE — ingresa de nuevo para detener)"})
                    continue
                definition = mod_cmds.get(cmd_name, "")
                desc = ""
                if isinstance(definition, dict):
                    shell = definition.get("shell", "")
                    desc = f"Ejecutar: {shell[:60]}{'…' if len(shell) > 60 else ''}"
                elif isinstance(definition, str):
                    desc = f"Ejecutar: {definition[:60]}{'…' if len(definition) > 60 else ''}"
                cmds.append({"cmd": cmd_name, "desc": desc})

    return cmds


def _help_no_mode() -> str:
    lines = ["Comandos disponibles:\n"]
    for c in _web_commands(None):
        lines.append(f"  {c['cmd']:<22} {c['desc']}")
    lines.append("\nUsa los tabs del header para cambiar de modo.")
    return "\n".join(lines)


# ── Handlers ──────────────────────────────────────────────────────────────────

async def index_handler(request: Request) -> HTMLResponse:
    html_path = STATIC / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


async def mods_handler(request: Request) -> JSONResponse:
    return JSONResponse(_all_mods_info())


async def commands_handler(request: Request) -> JSONResponse:
    return JSONResponse(_web_commands(_web_mode))


async def mode_handler(request: Request) -> JSONResponse:
    global _web_mode
    body = await request.json()
    key = body.get("mode", "").strip()
    with _lock:
        _web_mode = key if key else None
        agent_mod._active_mode = _web_mode or ""
        agent_mod._conversation_history.clear()
    return JSONResponse({"ok": True, "mode": _web_mode, "commands": _web_commands(_web_mode)})


async def chat_handler(request: Request) -> JSONResponse:
    body = await request.json()
    text = body.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "empty"}, status_code=400)

    text_lower = text.lower()

    # /watch → el frontend abre EventSource, no llega aquí; pero si llega igual manejarlo
    if text_lower == "/watch":
        return JSONResponse({"response": "__watch__"})

    if text_lower == "/help" and not _web_mode:
        return JSONResponse({"response": _help_no_mode()})

    loop = asyncio.get_running_loop()

    def _run() -> str:
        with _lock:
            if _web_mode is not None:
                agent_mod._active_mode = _web_mode
            return process(text)

    result = await loop.run_in_executor(None, _run)
    return JSONResponse({"response": _strip(result)})


async def watch_handler(request: Request):
    """Proxy SSE: reenvía el stream de localhost:8003/live al browser."""
    from sse_starlette.sse import EventSourceResponse
    import httpx

    async def event_generator():
        timeout = httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)
        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "GET",
                    MONITOR_SSE_URL,
                    headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
                    timeout=timeout,
                ) as resp:
                    if resp.status_code != 200:
                        yield {
                            "event": "error",
                            "data": json.dumps({
                                "msg": f"No se pudo conectar al monitor (HTTP {resp.status_code}). "
                                       "¿Está corriendo el servidor monitor?"
                            }),
                        }
                        return

                    yield {"event": "connected", "data": json.dumps({"msg": "Conectado al stream MQTT"})}

                    async for raw_line in resp.aiter_lines():
                        if await request.is_disconnected():
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
                            yield {
                                "event": "reading",
                                "data": json.dumps({
                                    "ts": ts,
                                    "litros": litros,
                                    "pct": pct,
                                    "dist": dist,
                                    "estado": estado,
                                    "line": f"[{ts}]  {litros:.0f} L  {pct:.1f}%  dist {dist:.1f} cm  {estado}",
                                }),
                            }
                        except Exception:
                            pass

        except Exception as exc:
            yield {
                "event": "error",
                "data": json.dumps({
                    "msg": f"No se pudo conectar al monitor ({exc}). "
                           "Asegúrate que el servidor monitor está corriendo."
                }),
            }

    return EventSourceResponse(event_generator())


# ── App factory ───────────────────────────────────────────────────────────────

def make_app() -> Starlette:
    return Starlette(routes=[
        Route("/", index_handler),
        Route("/api/mods",     mods_handler),
        Route("/api/commands", commands_handler),
        Route("/api/mode",     mode_handler,  methods=["POST"]),
        Route("/api/chat",     chat_handler,  methods=["POST"]),
        Route("/api/watch",    watch_handler),
    ])


def run_web(host: str = "0.0.0.0", port: int = 8080) -> None:
    import os
    import signal
    import subprocess
    import sys

    script = (
        "import uvicorn;"
        "from amanda_ia.web_server import make_app;"
        f"uvicorn.run(make_app(), host='{host}', port={port}, log_level='warning')"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", script],
        start_new_session=True,  # child in own session → no terminal SIGINT
    )

    def _stop(*_):
        proc.kill()
        print("\nServidor detenido.")
        os._exit(0)

    # El padre es Python puro sin asyncio — signal.signal funciona directamente
    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    print(f"amanda-IA web  →  http://localhost:{port}")
    print("Ctrl+C para detener")
    proc.wait()
