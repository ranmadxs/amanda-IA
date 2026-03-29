"""Servidor AIA Avatar — dashboard estilo Westworld en puerto AIA_AVATAR_PORT (default 3001).

Muestra en tiempo real: logs, pensamiento, memoria, modelo, versión, cwd.
Se conecta al agent_api para recibir el stream SSE.

Arranca automáticamente con `aia --web` o `aia --agent-api`.
"""

from __future__ import annotations

import json
import os
import socketserver
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"

# Buffer circular de los últimos eventos para nuevos clientes
_MAX_BUFFER = 200
_event_buffer: list[dict] = []
_buffer_lock = threading.Lock()
_sse_clients: list = []
_clients_lock = threading.Lock()


def _agent_api_url() -> str:
    from amanda_ia.config import get_ports
    return f"http://127.0.0.1:{get_ports()['agent_api']}"


def _push_event(kind: str, data: dict) -> None:
    """Agrega evento al buffer y lo transmite a todos los clientes SSE conectados."""
    event = {"kind": kind, "data": data, "ts": time.time()}
    with _buffer_lock:
        _event_buffer.append(event)
        if len(_event_buffer) > _MAX_BUFFER:
            _event_buffer.pop(0)
    payload = f"event: {kind}\ndata: {json.dumps(data)}\n\n".encode()
    with _clients_lock:
        dead = []
        for q in _sse_clients:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for q in dead:
            _sse_clients.remove(q)


def _ollama_info(model_name: str = "") -> dict:
    """Consulta Ollama /api/ps — context_length y size_vram están en el objeto del modelo."""
    try:
        req = urllib.request.Request("http://127.0.0.1:11434/api/ps")
        with urllib.request.urlopen(req, timeout=3) as resp:
            ps = json.loads(resp.read())
        models = ps.get("models") or []
        if models:
            m = models[0]
            return {
                "ollama_ok":      True,
                "ollama_vram_mb": m.get("size_vram", 0) / 1e6,
                "ollama_ctx_len": m.get("context_length", 0),
                "ollama_model":   m.get("name", ""),
                "ollama_params":  m.get("details", {}).get("parameter_size", ""),
                "ollama_quant":   m.get("details", {}).get("quantization_level", ""),
            }
        return {"ollama_ok": True, "ollama_vram_mb": 0, "ollama_ctx_len": 0,
                "ollama_model": "", "ollama_params": "", "ollama_quant": ""}
    except Exception:
        return {"ollama_ok": False, "ollama_vram_mb": 0, "ollama_ctx_len": 0,
                "ollama_model": "", "ollama_params": "", "ollama_quant": ""}


def _poll_agent_api() -> None:
    """Hilo daemon: consulta /info al agent_api cada 0.5s y emite stats.
    Ollama /api/ps se consulta cada 10 ciclos (~5s) para no saturarlo."""
    import psutil
    _ollama_cache = {"ollama_ok": False, "ollama_vram_mb": 0, "ollama_ctx_len": 0,
                     "ollama_model": "", "ollama_params": "", "ollama_quant": ""}
    _ollama_tick = 0
    while True:
        try:
            req = urllib.request.Request(f"{_agent_api_url()}/info")
            with urllib.request.urlopen(req, timeout=5) as resp:
                info = json.loads(resp.read())
            mem = psutil.virtual_memory()
            proc = psutil.Process(os.getpid())
            if _ollama_tick <= 0:
                _ollama_cache = _ollama_info(info.get("model", ""))
                _ollama_tick = 10
            else:
                _ollama_tick -= 1
            ollama = _ollama_cache
            _push_event("stats", {
                "version":        info.get("version", "?"),
                "model":          info.get("model", "?"),
                "cwd":            info.get("cwd", "?"),
                "mode":           info.get("mode", ""),
                "modColor":       info.get("modColor", "#ff8700"),
                "ram_total":      mem.total,
                "ram_used":       mem.used,
                "ram_pct":        mem.percent,
                "proc_mb":        proc.memory_info().rss / 1e6,
                "ctx_msgs":       info.get("ctx_msgs", 0),
                "ctx_tokens_est": info.get("ctx_tokens_est", 0),
                "ollama_vram_mb": ollama["ollama_vram_mb"],
                "ollama_ctx_len": ollama["ollama_ctx_len"],
                "ollama_ok":      ollama["ollama_ok"],
                "ollama_params":  ollama["ollama_params"],
                "ollama_quant":   ollama["ollama_quant"],
                "api_ok":         True,
            })
        except Exception:
            _push_event("stats", {"api_ok": False})
        time.sleep(0.5)


class _Queue:
    """Cola simple sin dependencias externas."""
    def __init__(self):
        self._items: list = []
        self._event = threading.Event()

    def put_nowait(self, item):
        self._items.append(item)
        self._event.set()

    def get(self, timeout=15):
        if not self._items:
            self._event.wait(timeout)
            self._event.clear()
        return self._items.pop(0) if self._items else None


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/avatar"):
            html = (STATIC / "avatar.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif path == "/avatar_speak":
            html = (STATIC / "avatar_speak.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif path == "/stream":
            self._handle_sse()
        elif path == "/mcps":
            self._proxy_json("/mcps")
        else:
            self.send_response(404)
            self.end_headers()

    def _proxy_json(self, endpoint: str) -> None:
        try:
            req = urllib.request.Request(f"{_agent_api_url()}{endpoint}")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read()
        except Exception:
            body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = _Queue()

        # Enviar buffer histórico al nuevo cliente
        with _buffer_lock:
            snapshot = list(_event_buffer)
        for ev in snapshot:
            try:
                payload = f"event: {ev['kind']}\ndata: {json.dumps(ev['data'])}\n\n".encode()
                self.wfile.write(payload)
            except OSError:
                return
        try:
            self.wfile.flush()
        except OSError:
            return

        with _clients_lock:
            _sse_clients.append(q)

        try:
            while True:
                payload = q.get(timeout=15)
                if payload is None:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(payload)
                self.wfile.flush()
        except OSError:
            pass
        finally:
            with _clients_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)


class _Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def run_aia_avatar(host: str = "0.0.0.0", port: int | None = None) -> _Server:
    """Levanta el servidor avatar en un hilo daemon. Retorna el servidor."""
    from amanda_ia.config import get_ports
    port = port if port is not None else get_ports()["avatar"]
    server = _Server((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=_poll_agent_api, daemon=True).start()
    return server, port


def push_log(entry: str) -> None:
    """Llamado desde agent_api para reenviar logs al avatar en tiempo real."""
    _push_event("log", {"entry": entry})


def push_think(entry: str) -> None:
    """Llamado desde agent_api para reenviar pensamientos al avatar."""
    _push_event("think", {"entry": entry})


def push_response(response: str) -> None:
    """Llamado desde agent_api al finalizar una respuesta."""
    _push_event("response", {"response": response})


def push_mcp(entry: str) -> None:
    """Llamado desde agent_api para reenviar llamadas MCP al avatar."""
    _push_event("mcp", {"entry": entry})


def push_memory(entry: str) -> None:
    """Llamado desde agent_api para reenviar eventos de memoria al avatar."""
    _push_event("memory", {"entry": entry})


def push_agilidad(entry: str) -> None:
    """Llamado desde agent_api para reenviar eventos de agilidad al avatar."""
    _push_event("agilidad", {"entry": entry})
