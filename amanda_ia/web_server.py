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
from amanda_ia.config import get_mods, get_mods_raw, server_in_modo
import amanda_ia.history as _history_mod

RESOURCES = Path(__file__).resolve().parent / "resources"
STATIC = Path(__file__).resolve().parent / "static"

MONITOR_SSE_URL = "http://localhost:8003/live"

# Procesa una petición a la vez (herramienta personal)
_lock = threading.Lock()
# Modo activo en la sesión web (None = modo general AiA)
_web_mode: str | None = None

_RICH_RE = re.compile(r"\[/?(?!AIA_IMG:)[^\]]*\]")  # excluye [AIA_IMG:...]
_IMG_RE = re.compile(r"\[AIA_IMG:[^\]]+\]")


def _strip(text: str) -> str:
    import urllib.parse
    # 1. Quitar Rich markup (no toca [AIA_IMG:...])
    text = _RICH_RE.sub("", text)
    # 2. Convertir rutas de imagen a URLs del endpoint
    def _img_to_url(m: re.Match) -> str:
        img_path = m.group(0)[9:-1]  # extrae path de [AIA_IMG:path]
        return f"[AIA_IMG:/api/image?path={urllib.parse.quote(img_path)}]"
    return _IMG_RE.sub(_img_to_url, text).strip()


def _load_banner(banner_name: str) -> str:
    path = RESOURCES / f"{banner_name}.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _all_mods_info() -> list[dict]:
    from amanda_ia.config import get_mcp_servers_raw
    mcp_raw = get_mcp_servers_raw()

    # MCPs globales: los que no tienen campo "modo" (disponibles en asistente general)
    global_mcps = [
        s.get("name", "") for s in mcp_raw
        if not s.get("modo") and s.get("enabled", True) is not False
    ]
    result = [{
        "name": "aia",
        "key": "",
        "displayName": "AiA",
        "banner": _load_banner("banner"),
        "color": "#7f8c8d",
        "colorDim": "#2c3e50",
        "mcpServers": global_mcps,
    }]
    for m in get_mods():
        key = m.get("key", "")
        # Servidores MCP configurados para este modo
        mode_mcps = [
            s.get("name", "") for s in mcp_raw
            if server_in_modo(s, key)
        ]
        result.append({
            "name": m.get("name"),
            "key": key,
            "displayName": m.get("name", "").capitalize(),
            "banner": _load_banner(m.get("banner", "banner")),
            "color": m.get("color", "#7f8c8d"),
            "colorDim": m.get("colorDim", "#2c3e50"),
            "mcpServers": mode_mcps,
        })
    return result


def _web_commands(mode_key: str | None) -> list[dict]:
    """Comandos slash disponibles para el modo actual en la web."""
    cmds: list[dict] = []
    cmds.append({"cmd": "/help",          "desc": "Listar herramientas disponibles del modo actual"})
    cmds.append({"cmd": "/resume",        "desc": "Retomar una conversación anterior"})
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
        from amanda_ia.agent import OLLAMA_MODEL
        model = OLLAMA_MODEL
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
        elif path == "/api/image":
            self._handle_image()
        elif path == "/api/history":
            self._send_json(_history_mod.list_all(_web_mode or ""))
        elif path == "/api/files":
            self._handle_files()
        elif path == "/api/file":
            self._handle_file_content()
        elif path == "/api/mongo/dbs":
            self._handle_mongo_dbs()
        elif path == "/api/mongo/collections":
            self._handle_mongo_collections()
        elif path == "/api/mongo/docs":
            self._handle_mongo_docs()
        else:
            self._send_json({"error": "not found"}, 404)

    # ── POST ──

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/mode":
            self._handle_mode(self._read_json())
        elif path == "/api/chat":
            self._handle_chat(self._read_json())
        elif path == "/api/history/load":
            self._handle_history_load(self._read_json())
        elif path == "/api/shell":
            self._handle_shell(self._read_json())
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
        from amanda_ia.config import get_mcp_servers_raw
        mcp_status = {s["name"]: s.get("enabled") is not False
                      for s in get_mcp_servers_raw() if s.get("name")}
        self._send_json({"ok": True, "mode": _web_mode, "commands": _web_commands(_web_mode), "mcpStatus": mcp_status})

    def _handle_chat(self, body: dict) -> None:
        text = body.get("text", "").strip()
        if not text:
            self._send_json({"error": "empty"}, 400)
            return

        text_lower = text.lower()

        # Respuestas inmediatas sin SSE
        if text_lower == "/watch":
            self._send_json({"response": "__watch__"})
            return
        if text_lower == "/resume":
            self._send_json({"response": "__resume__"})
            return
        if text_lower == "/help" and not _web_mode:
            self._send_json({"response": _help_no_mode()})
            return

        # ── SSE streaming: logs en paralelo a la ejecución ──────────────────
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def _sse(event: str, data: dict) -> None:
            try:
                msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
                self.wfile.write(msg.encode())
                self.wfile.flush()
            except OSError:
                pass

        phase: dict = {"value": "", "log": []}
        result_holder: list = [None]
        done = threading.Event()

        def _run() -> None:
            with _lock:
                if _web_mode is not None:
                    agent_mod._active_mode = _web_mode
                result_holder[0] = process(text, phase=phase)
            done.set()

        threading.Thread(target=_run, daemon=True).start()

        cursor = 0
        while not done.is_set():
            logs = phase.get("log", [])
            while cursor < len(logs):
                _sse("log", {"entry": logs[cursor]})
                cursor += 1
            done.wait(0.1)

        # flush logs restantes
        for entry in phase.get("log", [])[cursor:]:
            _sse("log", {"entry": entry})

        # Si el agente llamó start_live_monitor, activar modo watch
        pending = agent_mod._pending_live_action
        if pending == "start":
            agent_mod._pending_live_action = None
            _sse("response", {"response": "__watch__"})
        elif pending == "stop":
            agent_mod._pending_live_action = None
            _sse("response", {"response": _strip(result_holder[0] or "")})
        else:
            _sse("response", {"response": _strip(result_holder[0] or "")})

    def _handle_files(self) -> None:
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(self.path).query)
        dir_path = qs.get("path", [""])[0] or str(Path.cwd())
        p = Path(dir_path)
        if not p.is_dir():
            self._send_json({"error": "not a directory"}, 400)
            return
        try:
            entries = []
            items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for child in items:
                entries.append({
                    "name": child.name,
                    "path": str(child),
                    "isDir": child.is_dir(),
                    "ext": child.suffix.lstrip(".").lower() if child.is_file() else "",
                })
            self._send_json({"path": str(p), "entries": entries})
        except PermissionError:
            self._send_json({"error": "permission denied"}, 403)

    def _handle_file_content(self) -> None:
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(self.path).query)
        file_path = qs.get("path", [""])[0]
        p = Path(file_path)
        if not p.is_file():
            self._send_json({"error": "not a file"}, 404)
            return
        try:
            if p.stat().st_size > 500_000:
                self._send_json({"error": "file too large"}, 413)
                return
            content = p.read_text(encoding="utf-8", errors="replace")
            self._send_json({"path": str(p), "content": content, "ext": p.suffix.lstrip(".").lower()})
        except PermissionError:
            self._send_json({"error": "permission denied"}, 403)

    def _handle_history_load(self, body: dict) -> None:
        global _web_mode
        mode = body.get("mode", _web_mode or "")
        hid  = body.get("id", "")
        messages = _history_mod.load(mode, hid)
        if messages is None:
            self._send_json({"error": "not found"}, 404)
            return
        with _lock:
            agent_mod._active_mode = mode
            agent_mod._conversation_history = messages
        self._send_json({"ok": True})

    def _handle_image(self) -> None:
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(self.path).query)
        img_path = qs.get("path", [""])[0]
        p = Path(img_path)
        if not p.exists() or p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            self._send_json({"error": "not found"}, 404)
            return
        data = p.read_bytes()
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}.get(p.suffix.lower().lstrip("."), "image/png")
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    # ── Shell terminal ──

    def _handle_shell(self, body: dict) -> None:
        import os
        import subprocess
        cmd = (body.get("cmd") or "").strip()
        cwd = (body.get("cwd") or "").strip() or os.getcwd()
        if not cmd:
            self._send_json({"error": "cmd required"}, 400)
            return
        _interactive = ("vim", "vi", "nano", "less", "more", "top", "htop",
                        "man", "watch", "ssh", "ftp", "python", "ipython",
                        "bash", "zsh", "sh", "fish")
        first_word = cmd.split()[0].split("/")[-1]
        if first_word in _interactive:
            self._send_json({"stdout": "", "stderr": f"'{first_word}' es interactivo y no puede correr aquí.", "returncode": 1})
            return
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=30, cwd=cwd
            )
            self._send_json({"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode})
        except subprocess.TimeoutExpired:
            self._send_json({"stdout": "", "stderr": "Timeout (30s).", "returncode": -1})
        except Exception as e:
            self._send_json({"stdout": "", "stderr": str(e), "returncode": -1})

    # ── MongoDB explorer ──

    def _handle_mongo_dbs(self) -> None:
        import os
        mongodb_uri = os.getenv("MONGODB_URI", "")
        if not mongodb_uri:
            self._send_json({"error": "MONGODB_URI not set"}, 503)
            return
        try:
            from pymongo import MongoClient
            client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=3000)
            dbs = [d["name"] for d in client.list_databases() if d["name"] not in ("admin", "local", "config")]
            self._send_json({"dbs": dbs})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_mongo_collections(self) -> None:
        import os
        from urllib.parse import parse_qs, urlparse
        mongodb_uri = os.getenv("MONGODB_URI", "")
        if not mongodb_uri:
            self._send_json({"error": "MONGODB_URI not set"}, 503)
            return
        qs = parse_qs(urlparse(self.path).query)
        db_name = qs.get("db", [""])[0]
        if not db_name:
            self._send_json({"error": "db param required"}, 400)
            return
        try:
            from pymongo import MongoClient
            client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=3000)
            db = client[db_name]
            cols = []
            for col_name in sorted(db.list_collection_names()):
                count = db[col_name].estimated_document_count()
                cols.append({"name": col_name, "count": count})
            self._send_json({"collections": cols})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def _handle_mongo_docs(self) -> None:
        import os
        from urllib.parse import parse_qs, urlparse
        mongodb_uri = os.getenv("MONGODB_URI", "")
        if not mongodb_uri:
            self._send_json({"error": "MONGODB_URI not set"}, 503)
            return
        qs = parse_qs(urlparse(self.path).query)
        db_name = qs.get("db", [""])[0]
        col_name = qs.get("col", [""])[0]
        limit = int(qs.get("limit", ["50"])[0])
        if not db_name or not col_name:
            self._send_json({"error": "db and col params required"}, 400)
            return
        try:
            from bson import ObjectId
            from pymongo import MongoClient
            client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=3000)
            docs = list(client[db_name][col_name].find({}, limit=limit))
            # Convert non-serializable BSON types
            from datetime import datetime as _dt, date as _date
            def _convert(obj):
                if isinstance(obj, ObjectId):
                    return str(obj)
                if isinstance(obj, (_dt, _date)):
                    return obj.isoformat()
                if isinstance(obj, dict):
                    return {k: _convert(v) for k, v in obj.items()}
                if isinstance(obj, list):
                    return [_convert(i) for i in obj]
                return obj
            self._send_json({"docs": _convert(docs)})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

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
