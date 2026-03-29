"""API HTTP del agente AIA — corre en puerto 8081 (loopback).

Desacopla el agente de la capa web: web_server.py se comunica con el
agente exclusivamente vía HTTP en lugar de imports directos.

Uso:
    aia --web          # levanta agent_api (8081) + web_server (8080)
    aia --agent-api    # solo el API, sin UI web
"""

from __future__ import annotations

import json
import os
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import amanda_ia.agent as agent_mod
from amanda_ia.agent import process, request_interrupt
import amanda_ia.history as _history_mod

_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # silenciar logs de acceso
        pass

    # ── helpers ──

    def _send_json(self, data: object, status: int = 200) -> None:
        try:
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── routing ──

    def do_OPTIONS(self) -> None:
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/health":
            self._send_json({"status": "ok"})
        elif path == "/info":
            self._send_json(self._get_info())
        elif path == "/history":
            from urllib.parse import parse_qs, urlparse
            mode = parse_qs(urlparse(self.path).query).get("mode", [""])[0]
            self._send_json(_history_mod.list_all(mode))
        elif path == "/mcps":
            self._send_json(self._get_mcps())
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        body = self._read_json()
        if path == "/chat":
            self._handle_chat(body)
        elif path == "/interrupt":
            request_interrupt((body or {}).get("reason", "user"))
            self._send_json({"ok": True})
        elif path == "/mode":
            self._handle_mode(body)
        elif path == "/history/load":
            self._handle_history_load(body)
        elif path == "/history/flush":
            mode = (body or {}).get("mode", agent_mod._active_mode or "")
            if hasattr(_history_mod, "delete_all"):
                _history_mod.delete_all(mode)
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)

    # ── handlers ──

    def _get_mcps(self) -> dict:
        try:
            from amanda_ia.config import get_mcp_servers
            names = [s.get("name", "?") for s in get_mcp_servers() if s.get("name")]
        except Exception:
            names = []
        return {"mcps": names}

    def _get_info(self) -> dict:
        try:
            import tomllib
            toml = tomllib.loads(
                (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
            )
            version = toml["tool"]["poetry"]["version"]
        except Exception:
            version = "?"
        mod = agent_mod._get_mod_config()
        mod_color = (mod.get("color") if mod else None) or "#ff8700"
        history = agent_mod._conversation_history
        ctx_msgs = len(history)
        ctx_chars = sum(len(str(m.get("content", ""))) for m in history)
        ctx_tokens_est = ctx_chars // 4
        return {
            "version": version,
            "model": agent_mod.OLLAMA_MODEL,
            "cwd": os.getcwd(),
            "mode": agent_mod._active_mode or "",
            "modColor": mod_color,
            "ctx_msgs": ctx_msgs,
            "ctx_tokens_est": ctx_tokens_est,
        }

    def _handle_mode(self, body: dict) -> None:
        key = (body or {}).get("mode", "").strip()
        with _lock:
            agent_mod._active_mode = key if key else None
            agent_mod._conversation_history.clear()
        self._send_json({"ok": True, "mode": agent_mod._active_mode or ""})

    def _handle_history_load(self, body: dict) -> None:
        mode = (body or {}).get("mode", agent_mod._active_mode or "")
        hid = (body or {}).get("id", "")
        messages = _history_mod.load(mode, hid)
        if messages is None:
            self._send_json({"error": "not found"}, 404)
            return
        with _lock:
            agent_mod._active_mode = mode
            agent_mod._conversation_history = messages
        self._send_json({"ok": True, "messages": [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in ("user", "assistant") and m.get("content")
        ]})

    def _handle_chat(self, body: dict) -> None:
        text = (body or {}).get("text", "").strip()
        if not text:
            self._send_json({"error": "empty"}, 400)
            return

        # Si el caller indica modo, sincronizarlo antes de procesar
        mode = (body or {}).get("mode")
        if mode is not None:
            agent_mod._active_mode = mode if mode else None

        # Respuesta SSE
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        client_gone = threading.Event()

        def _sse(event: str, data: dict) -> None:
            try:
                self.wfile.write(f"event: {event}\ndata: {json.dumps(data)}\n\n".encode())
                self.wfile.flush()
            except OSError:
                client_gone.set()
                request_interrupt("client disconnected")

        class _NotifyList(list):
            def __init__(self):
                super().__init__()
                self._event = threading.Event()

            def append(self, item):
                super().append(item)
                self._event.set()

        try:
            from amanda_ia import aia_avatar as _avatar
        except ImportError:
            _avatar = None

        class _AvatarNotifyList(_NotifyList):
            def __init__(self, push_fn, wake=None):
                super().__init__()
                self._push_fn = push_fn
                self._wake = wake
            def append(self, item):
                super().append(item)
                if _avatar and self._push_fn:
                    try: self._push_fn(item)
                    except Exception: pass
                if self._wake:
                    self._wake.set()

        log_list     = _AvatarNotifyList(_avatar.push_log      if _avatar else None)
        think_list   = _AvatarNotifyList(_avatar.push_think    if _avatar else None)
        mcp_list     = _AvatarNotifyList(_avatar.push_mcp      if _avatar else None, wake=log_list._event)
        memory_list  = _AvatarNotifyList(_avatar.push_memory   if _avatar else None, wake=log_list._event)
        agil_list    = _AvatarNotifyList(_avatar.push_agilidad if _avatar else None, wake=log_list._event)
        phase: dict  = {"value": "", "log": log_list, "think_log": think_list, "mcp_log": mcp_list, "memory_log": memory_list, "agilidad": agil_list}
        result_holder: list = [None]
        done = threading.Event()

        def _run() -> None:
            with _lock:
                result_holder[0] = process(text, phase=phase)
            done.set()
            log_list._event.set()
            think_list._event.set()
            mcp_list._event.set()
            memory_list._event.set()
            agil_list._event.set()

        threading.Thread(target=_run, daemon=True).start()

        cursor = 0
        think_cursor = 0
        mcp_cursor = 0
        mem_cursor = 0
        agil_cursor = 0

        # Loop principal: espera log. Think, mcp, memory y agilidad se drenan oportunísticamente.
        while not done.is_set() or cursor < len(log_list) or mcp_cursor < len(mcp_list) or mem_cursor < len(memory_list) or agil_cursor < len(agil_list):
            if client_gone.is_set():
                break
            while cursor < len(log_list):
                _sse("log", {"entry": log_list[cursor]})
                cursor += 1
            while think_cursor < len(think_list):
                _sse("think", {"entry": think_list[think_cursor]})
                think_cursor += 1
            while mcp_cursor < len(mcp_list):
                _sse("mcp", {"entry": mcp_list[mcp_cursor]})
                mcp_cursor += 1
            while mem_cursor < len(memory_list):
                _sse("memory", {"entry": memory_list[mem_cursor]})
                mem_cursor += 1
            while agil_cursor < len(agil_list):
                _sse("agilidad", {"entry": agil_list[agil_cursor]})
                agil_cursor += 1
            if not done.is_set():
                log_list._event.wait(timeout=5.0)
                log_list._event.clear()

        if client_gone.is_set():
            return

        # Flush pendiente
        for entry in log_list[cursor:]:
            _sse("log", {"entry": entry})
            cursor += 1
        for entry in mcp_list[mcp_cursor:]:
            _sse("mcp", {"entry": entry})
            mcp_cursor += 1
        for entry in memory_list[mem_cursor:]:
            _sse("memory", {"entry": entry})
            mem_cursor += 1
        for entry in agil_list[agil_cursor:]:
            _sse("agilidad", {"entry": entry})
            agil_cursor += 1

        result = result_holder[0] or ""
        if result.startswith("__interrupted__:"):
            reason = result[len("__interrupted__:"):]
            _sse("response", {"response": f"❗ {reason}", "interrupted": True})
            _sse("done", {})
            return

        pending = agent_mod._pending_live_action
        if pending == "start":
            agent_mod._pending_live_action = None
            _sse("response", {"response": "__watch__"})
        elif pending == "stop":
            agent_mod._pending_live_action = None
            _sse("response", {"response": result})
        else:
            _sse("response", {"response": result})
            if _avatar:
                try: _avatar.push_response(result)
                except Exception: pass

        # Esperar al planning thread y flush final del canal think (después de mostrar la respuesta)
        plan_thread = phase.get("_plan_thread")
        if plan_thread and plan_thread.is_alive():
            plan_thread.join(timeout=30)
        for entry in think_list[think_cursor:]:
            _sse("think", {"entry": entry})
            think_cursor += 1
        for entry in mcp_list[mcp_cursor:]:
            _sse("mcp", {"entry": entry})
            mcp_cursor += 1
        for entry in memory_list[mem_cursor:]:
            _sse("memory", {"entry": entry})
            mem_cursor += 1
        for entry in agil_list[agil_cursor:]:
            _sse("agilidad", {"entry": entry})
            agil_cursor += 1

        # Emitir la respuesta real del LLM en el canal think como "Pensamiento Respuesta"
        # (incluye gráficos [AIA_IMG:...] y el texto completo de la respuesta)
        if phase.get("_plan_thread") is not None and not result.startswith("__interrupted__:"):
            _sse("think", {"entry": f"Pensamiento Respuesta ?> {result}"})

        _sse("done", {})


class _Server(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            return
        super().handle_error(request, client_address)


def run_agent_api(host: str = "127.0.0.1", port: int | None = None) -> _Server:
    from amanda_ia.config import get_ports
    port = port if port is not None else get_ports()["agent_api"]
    """Levanta el agent API en un hilo daemon. Retorna el servidor."""
    server = _Server((host, port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
