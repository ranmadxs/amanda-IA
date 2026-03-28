"""Servidor web chatbot para amanda-IA.

Uso:
    aia --web           # puerto 8080
    aia --web --port 3000
"""

from __future__ import annotations

import json
import re
import socketserver
import threading
import urllib.error
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

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


def _server_info() -> dict:
    """Versión, modelo Ollama y directorio de trabajo."""
    import os
    try:
        import tomllib
        _toml = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())
        version = _toml["tool"]["poetry"]["version"]
    except Exception:
        version = "?"
    try:
        from amanda_ia.config import get_config
        cfg = get_config()
        model = cfg.get("model", "?")
    except Exception:
        model = "?"
    return {"version": version, "model": model, "cwd": os.getcwd()}


def _help_no_mode() -> str:
    lines = ["Comandos disponibles:\n"]
    for c in _web_commands(None):
        lines.append(f"  {c['cmd']:<22} {c['desc']}")
    lines.append("\nUsa los tabs del header para cambiar de modo.")
    return "\n".join(lines)


# ── Handler HTTP ───────────────────────────────────────────────────────────────

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silenciar logs de acceso
        pass

    # ── helpers ──

    def _send_json(self, data: object, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    # ── GET ──

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/":
            self._send_html((STATIC / "index.html").read_text(encoding="utf-8"))
        elif path == "/api/mods":
            self._send_json(_all_mods_info())
        elif path == "/api/commands":
            self._send_json(_web_commands(_web_mode))
        elif path == "/api/info":
            self._send_json(_server_info())
        elif path == "/api/watch":
            self._handle_watch()
        else:
            self._send_json({"error": "not found"}, 404)

    # ── POST ──

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/mode":
            self._handle_mode(self._read_json())
        elif path == "/api/chat":
            self._handle_chat(self._read_json())
        else:
            self._send_json({"error": "not found"}, 404)

    # ── rutas ──

    def _handle_mode(self, body: dict) -> None:
        global _web_mode
        key = body.get("mode", "").strip()
        with _lock:
            _web_mode = key if key else None
            agent_mod._active_mode = _web_mode or ""
            agent_mod._conversation_history.clear()
        self._send_json({"ok": True, "mode": _web_mode, "commands": _web_commands(_web_mode)})

    def _handle_chat(self, body: dict) -> None:
        text = body.get("text", "").strip()
        if not text:
            self._send_json({"error": "empty"}, 400)
            return

        text_lower = text.lower()

        if text_lower == "/watch":
            self._send_json({"response": "__watch__"})
            return

        if text_lower == "/help" and not _web_mode:
            self._send_json({"response": _help_no_mode()})
            return

        def _run() -> str:
            with _lock:
                if _web_mode is not None:
                    agent_mod._active_mode = _web_mode
                return process(text)

        result = _run()
        self._send_json({"response": _strip(result)})

    def _handle_watch(self) -> None:
        """SSE: reenvía el stream de localhost:8003/live al browser."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def send_event(event: str, data: dict) -> None:
            try:
                msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
                self.wfile.write(msg.encode())
                self.wfile.flush()
            except OSError:
                pass

        try:
            req = urllib.request.Request(
                MONITOR_SSE_URL,
                headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                send_event("connected", {"msg": "Conectado al stream MQTT"})
                for raw_line in resp:
                    line = raw_line.decode(errors="replace").strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        litros = float(data.get("litros") or 0)
                        pct    = float(data.get("porcentaje") or 0)
                        dist   = float(data.get("distancia") or 0)
                        estado = data.get("estado", "?")
                        ts     = datetime.now().strftime("%H:%M:%S")
                        send_event("reading", {
                            "ts": ts,
                            "litros": litros,
                            "pct": pct,
                            "dist": dist,
                            "estado": estado,
                            "line": f"[{ts}]  {litros:.0f} L  {pct:.1f}%  dist {dist:.1f} cm  {estado}",
                        })
                    except Exception:
                        pass
        except Exception as exc:
            send_event("error", {"msg": (
                f"No se pudo conectar al monitor ({exc}). "
                "Asegúrate que el servidor monitor está corriendo."
            )})


# ── Servidor ───────────────────────────────────────────────────────────────────

class _Server(socketserver.ThreadingMixIn, HTTPServer):
    """HTTP multihilo con daemon_threads para que Ctrl+C lo mate limpio."""
    daemon_threads = True


def run_web(host: str = "0.0.0.0", port: int = 8080) -> None:
    import os
    import signal
    import threading

    # Self-pipe trick: el handler escribe un byte; el main thread lee del pipe.
    # Funciona en cualquier entorno sin importar cómo Python gestiona las señales.
    _r, _w = os.pipe()

    def _stop(*_):
        try:
            os.write(_w, b"x")
        except OSError:
            pass

    signal.signal(signal.SIGINT,  _stop)
    signal.signal(signal.SIGTERM, _stop)

    server = _Server((host, port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    try:
        import tomllib
        _toml = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())
        _version = _toml["tool"]["poetry"]["version"]
    except Exception:
        _version = "?"

    print(f"amanda-IA v{_version}  →  http://localhost:{port}")
    print("Ctrl+C para detener")

    # DEBUG: verificar estado del terminal
    try:
        import termios, sys
        if sys.stdin.isatty():
            attrs = termios.tcgetattr(sys.stdin.fileno())
            lflag = attrs[3]
            isig_on = bool(lflag & termios.ISIG)
            print(f"[debug] ISIG={'ON' if isig_on else 'OFF (Ctrl+C no manda SIGINT!)'}", flush=True)
        else:
            print("[debug] stdin no es tty", flush=True)
    except Exception as e:
        print(f"[debug] no pude leer terminal: {e}", flush=True)

    # Bloquea hasta que _stop escriba en el pipe (SIGINT o SIGTERM)
    try:
        os.read(_r, 1)
    except OSError:
        pass
    finally:
        os.close(_r)
        os.close(_w)

    print("\nServidor detenido.")
    os._exit(0)
