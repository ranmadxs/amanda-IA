"""Agente base - arquetipo para extender."""

import asyncio
import json
import logging
import re
import os
import subprocess
import time
import unicodedata
from pathlib import Path
import tomllib

# ── Logger permanente en build/ ────────────────────────────────────────────────
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
_BUILD_DIR.mkdir(exist_ok=True)
_LOG_FILE = _BUILD_DIR / f"aia_{time.strftime('%Y%m%d')}.log"
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(_LOG_FILE, encoding="utf-8")],
)
logger = logging.getLogger("aia")

from importlib.resources import files
from amanda_ia.llm_client import llm_chat, llm_generate, set_llm_hooks
from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.eventloop.utils import call_soon_threadsafe, run_in_executor_with_context
from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType


def _scroll_window_up(w: "Window", b: "Buffer", step: int = 3) -> None:
    """Scrollea la ventana `w` hacia arriba `step` líneas visuales."""
    if not (w and w.render_info):
        return
    first_row = w.render_info.first_visible_line()
    b.cursor_position = b.document.translate_row_col_to_index(first_row, 0)
    w.vertical_scroll = max(0, w.render_info.vertical_scroll - step)


def _scroll_window_down(w: "Window", b: "Buffer", step: int = 3) -> None:
    """Scrollea la ventana `w` hacia abajo `step` líneas visuales."""
    if not (w and w.render_info):
        return
    last_row = w.render_info.last_visible_line()
    max_row = max(0, b.document.line_count - 1)
    b.cursor_position = b.document.translate_row_col_to_index(min(last_row, max_row), 0)
    w.vertical_scroll = w.render_info.vertical_scroll + step


class _ScrollableBufferControl(BufferControl):
    """
    BufferControl para el output.
    - click: manejado por focus_on_click=True (comportamiento original)
    - scroll rueda: delegado a _scroll_window_up/down via Keys.ScrollUp/Down
    """
    _window: "Window | None" = None  # inyectado después de crear el Window
from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.page_navigation import (
    scroll_page_up,
    scroll_page_down,
)
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import DynamicStyle, Style, merge_styles

from rich.console import Console

from amanda_ia.tools import get_tools, execute_tool
from amanda_ia.tools.registry import set_tool_hooks
from amanda_ia.config import get_mcp_display_names, get_mcp_servers, get_mcp_servers_raw, set_mcp_server_enabled
from amanda_ia.config import get_mods_raw, get_mods, set_mod_enabled
from amanda_ia.config import _project_root, server_in_modo
from amanda_ia.mcp_client import get_mcp_server_info, invalidate_mcp_cache, get_server_name_for_tool, get_server_transport, get_mode_help, list_tools_for_server, call_tool_on_server
from amanda_ia.classifier import classify_prompt, CLASSIFIER_MODEL
from amanda_ia.classifier_cache import get as cache_get, set_ as cache_set, delete_all as cache_delete_all
from amanda_ia.plan_cache import get as plan_cache_get, set_ as plan_cache_set, delete_all as plan_cache_delete_all
from amanda_ia import live_monitor
from amanda_ia.feedback import save_feedback
from amanda_ia.memory_hooks import set_hook as _set_memory_hook
from amanda_ia.agilidad_hooks import install as _agil_install, uninstall as _agil_uninstall, emit as _agil_emit
import amanda_ia.history as _history_mod

console = Console()


OLLAMA_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")
COAGITATOR_MODEL = os.environ.get("AIA_COAGITATOR_MODEL", OLLAMA_MODEL)
# num_ctx: M1 Pro 16GB + 14.8B Q4_K_M (~9.5GB modelo) → ~4GB libres para KV cache.
# KV cache ≈ 128KB/tok (GQA 14B) → 16384 tok = ~2GB, deja 2GB de margen.
# Configurable con AIA_OLLAMA_NUM_CTX si se cambia el modelo.
_OLLAMA_OPTIONS: dict = {"num_ctx": int(os.environ.get("AIA_OLLAMA_NUM_CTX", "16384"))}

# Caché de rama git: (ruta, tiempo_última_consulta, branch)
_git_branch_cache: tuple[str, float, str] | None = None
_GIT_BRANCH_TTL = 5.0  # segundos entre consultas a git

# ── Interrupción del agente ────────────────────────────────────────────────────
import threading as _threading
_interrupt_event = _threading.Event()
_interrupt_reason: str = ""

def request_interrupt(reason: str = "user") -> None:
    global _interrupt_reason
    _interrupt_reason = reason
    _interrupt_event.set()

def clear_interrupt() -> None:
    global _interrupt_reason
    _interrupt_reason = ""
    _interrupt_event.clear()


def _get_git_branch(cwd: str) -> str | None:
    """Retorna la rama git actual del directorio, con caché de 5s. None si no es un repo."""
    global _git_branch_cache
    now = time.monotonic()
    if _git_branch_cache and _git_branch_cache[0] == cwd and now - _git_branch_cache[1] < _GIT_BRANCH_TTL:
        return _git_branch_cache[2] or None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=2,
        )
        branch = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        branch = ""
    _git_branch_cache = (cwd, now, branch)
    return branch or None


SYSTEM_PROMPT_BASE = """Eres un asistente útil. Tienes acceso a herramientas (tools) configuradas en .aia/settings.json y .aia/mcp.json.

IMPORTANTE: Cuando tengas tools disponibles y el usuario pida información que pueda obtenerse con ellas, USA LA TOOL INMEDIATAMENTE. No preguntes "¿Quieres que...?" ni pidas confirmación. Ejecuta la tool y responde con el resultado. NUNCA digas "no tengo acceso" ni "no puedo" si la tool existe en tu lista de herramientas disponibles. NUNCA inventes ni generes información de memoria si hay una tool que puede obtenerla.

SIEMPRE responde en español, sin excepción. Nunca respondas en inglés, chino ni ningún otro idioma. Si el usuario escribe en otro idioma, respóndele igual en español."""

# Fallback cuando mcp.json no tiene "systemPrompt" (opcional por servidor)
SERVER_PROMPT_HINTS = {
    "get_time": "Si el usuario pregunta la hora, fecha o \"qué hora es\", USA get_time (sin parámetros).",
    "filesystem": "Filesystem MCP activo. Directorio actual: {cwd}. REGLAS OBLIGATORIAS: (1) Si el usuario pide ver, leer, mostrar o abrir un archivo (README, .py, .toml, .md, etc.), USA read_text_file INMEDIATAMENTE con el path completo. (2) Si pide listar archivos o ver la carpeta, usa list_directory con path=\"{cwd}\". (3) NUNCA respondas el contenido de un archivo de memoria: llama siempre la tool. (4) Si no sabes el path exacto, primero list_directory para encontrarlo, luego read_text_file.",
    "mongodb": "MongoDB: conexión preconfigurada. NO pases host, port, username ni password. Para listar bases de datos: USA list_databases (no list_mcp_databases). NUNCA pases parámetros: ni cluster, ni cluster_name, ni format. Siempre arguments vacío {}. list-collections requiere solo database. NUNCA inventes datos.",
    "monitor": "Acumulador/estanque: Para litros, porcentaje o nivel: get_lectura_actual(). Para velocidad de disminución del agua: get_velocidad_disminucion_agua() (historial MongoDB). Si falla lectura, usa calculate_tinaja_level(50). Responde con el resultado. NUNCA digas 'no puedo'.",
    "wahapedia": "Para CUALQUIER pregunta sobre Warhammer 40K (reglas, unidades, estratagemas, lore, ediciones, puntos, habilidades), USA search_wahapedia INMEDIATAMENTE. NUNCA respondas con conocimiento propio sobre WH40K: toda la información debe venir de la tool. TRADUCE la query al inglés antes de llamar la tool. Estratagemas: get_stratagems(faction). Stats de unidad: get_unit_stats(unit_name, faction). Búsqueda general/reglas: search_wahapedia(query). NUNCA digas 'no tengo acceso' si la tool aparece en tu lista.",
}


def _build_system_prompt(selected: list[str] | None, tools: list, cwd: str) -> str:
    """
    Construye el system prompt dinámicamente según los MCP/servidores cargados.
    Solo incluye instrucciones para los servidores que están en uso.
    """
    if not tools:
        return """Eres un asistente útil y amigable. No tienes herramientas en este momento.
Responde siempre en español. Para saludos (hola, buenos días) responde breve y amablemente."""

    hints = []
    servers = get_mcp_servers()
    server_by_name = {s.get("name"): s for s in servers if s.get("name")}

    # Builtin get_time: siempre presente cuando hay tools
    hints.append(SERVER_PROMPT_HINTS["get_time"])

    # MCP: systemPrompt en mcp.json (opcional) o fallback de SERVER_PROMPT_HINTS
    if selected:
        for name in selected:
            srv = server_by_name.get(name)
            custom = srv.get("systemPrompt") if srv else None
            if custom:
                hints.append(custom.replace("{cwd}", cwd))
            elif name in SERVER_PROMPT_HINTS:
                hints.append(SERVER_PROMPT_HINTS[name].format(cwd=cwd))

    import datetime as _dt
    _today = _dt.date.today().strftime("%d de %B de %Y").replace(
        "January","enero").replace("February","febrero").replace("March","marzo").replace(
        "April","abril").replace("May","mayo").replace("June","junio").replace(
        "July","julio").replace("August","agosto").replace("September","septiembre").replace(
        "October","octubre").replace("November","noviembre").replace("December","diciembre")
    _date_hint = f"Fecha actual: {_today}. El año en curso es {_dt.date.today().year}. Los datos de {_dt.date.today().year} SÍ existen y DEBEN obtenerse con las tools disponibles."
    parts = [SYSTEM_PROMPT_BASE + f"\n\n{_date_hint}"]
    if hints:
        parts.append("\n\n" + "\n\n".join(f"IMPORTANTE: {h}" for h in hints))
    # Extra del modo activo (ej: spanglish para Warhammer 40K)
    mod = _get_mod_config()
    if mod and mod.get("systemPromptExtra"):
        extra = mod["systemPromptExtra"].replace("{cwd}", cwd)
        parts.append(f"\n\nIMPORTANTE: {extra}")
    else:
        parts.append("\n\nIMPORTANTE: Responde siempre en español. La respuesta final debe estar en español.")

    # Contexto del proyecto: si el modo define contextFile, inyectarlo en el prompt
    if mod and mod.get("contextFile"):
        context_path = Path(cwd) / mod["contextFile"]
        if context_path.exists():
            try:
                context_content = context_path.read_text(encoding="utf-8").strip()
                parts.append(f"\n\n--- CONTEXTO DEL PROYECTO ({mod['contextFile']}) ---\n{context_content}\n--- FIN CONTEXTO ---")
            except Exception:
                pass

    return "\n".join(parts)


def _get_version() -> str:
    """Versión desde pyproject.toml."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    return data["tool"]["poetry"]["version"]


def _load_banner(name: str = "banner") -> list[str]:
    """Carga resources/{name}.txt. Si no existe, usa banner.txt por defecto."""
    try:
        path = files("amanda_ia") / "resources" / f"{name}.txt"
        return path.read_text().strip("\n").split("\n")
    except Exception:
        path = files("amanda_ia") / "resources" / "banner.txt"
        return path.read_text().strip("\n").split("\n")


def _disp_width(s: str) -> int:
    """Ancho visual de una cadena contando caracteres ambiguos (█) como 2 columnas."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F", "A") else 1 for c in s)


def _ljust_disp(s: str, width: int) -> str:
    """Padea s con espacios hasta alcanzar el ancho visual `width`."""
    return s + " " * max(0, width - _disp_width(s))


def _get_header_formatted_text():
    """Header como formatted text para prompt_toolkit (banner + textos + rule)."""
    cwd = os.getcwd()
    if _active_mode:
        servers = get_mcp_servers()
        mode_servers = _get_servers_by_mode(servers, _active_mode, as_list=True)
        global_srv = _get_global_servers(servers)
        mode_names_set = {s["name"] for s in mode_servers}
        combined = [s["name"] for s in mode_servers] + [s["name"] for s in global_srv if s["name"] not in mode_names_set]
        mcp_info = ", ".join(combined) if combined else None
    else:
        # Solo MCPs del pool general (sin modo); los de modo no se usan aquí
        servers = get_mcp_servers()
        general = _get_servers_for_general_mode(servers)
        names = [s.get("name") for s in general if s.get("name")]
        mcp_info = ", ".join(names) if names else get_mcp_server_info()
    tools_label = f"Ollama + {mcp_info}" if mcp_info else "Ollama + Tools"
    texts = [
        f"aia v{_get_version()}",
        f"{OLLAMA_MODEL} · {tools_label}",
        f"{cwd}",
    ]
    mod = _get_mod_config()
    active_banner_lines = _load_banner(mod.get("banner", "banner")) if mod else _load_banner()
    active_color = mod.get("color", "#ff8700") if mod else "#ff8700"
    max_icon_width = max((_disp_width(l) for l in active_banner_lines), default=0)
    lines = []
    num_lines = 5
    for i in range(num_lines):
        combined_icon = active_banner_lines[i] if i < len(active_banner_lines) else ""
        txt = texts[i] if i < len(texts) else ""
        if combined_icon:
            banner_style = f"bold fg:{active_color}"
            lines.append((banner_style, _ljust_disp(combined_icon, max_icon_width)))
        if txt:
            lines.append(("fg:ansigray", "  " + txt if combined_icon else txt))
        lines.append(("", "\n"))
    rule = "─" * 50 + "\n"
    lines.append(("fg:ansigray", rule))
    return lines


def _create_header_window() -> Window:
    """Ventana fija con el header (banner + textos + rule)."""
    return Window(
        content=FormattedTextControl(_get_header_formatted_text),
        height=Dimension(min=9),
        dont_extend_height=True,
    )


def _strip_rich_markup(text: str) -> str:
    """Quita tags [dim], [/], etc. de Rich para mostrar en prompt_toolkit."""
    return re.sub(r"\[/?[^\]]*\]", "", text)




def _translate_to_english(text: str) -> str:
    """Traduce texto al inglés usando Ollama. Para Wahapedia."""
    if not text or not text.strip():
        return text
    try:
        r = llm_chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": f"Traduce SOLO al inglés, sin explicaciones. Responde únicamente con la traducción:\n{text.strip()}",
                }
            ],
            purpose="translate_en",
            options=_OLLAMA_OPTIONS,
        )
        out = (getattr(r.message, "content", None) or "").strip()
        return out if out else text
    except Exception:
        return text


# Alias de facciones: nombre común -> slug Wahapedia
_WAHAPEDIA_FACTION_ALIASES: dict[str, str] = {
    "ultramarines": "space-marines",
    "space-marines": "space-marines",
    "space marines": "space-marines",
    "marines espaciales": "space-marines",
    "marines": "space-marines",
    "custodes": "adeptus-custodes",
    "adepta sororitas": "adepta-sororitas",
    "hermanas de batalla": "adepta-sororitas",
    "mechanicus": "adeptus-mechanicus",
    "guardia imperial": "astra-militarum",
    "grey knights": "grey-knights",
    "caballeros imperiales": "imperial-knights",
    "chaos daemons": "chaos-daemons",
    "chaos knights": "chaos-knights",
    "marines del caos": "chaos-space-marines",
    "death guard": "death-guard",
    "mil hijos": "thousand-sons",
    "world eaters": "world-eaters",
    "eldar": "aeldari",
    "dark eldar": "drukhari",
    "cultos genestealer": "genestealer-cults",
    "votann": "leagues-of-votann",
}


def _translate_wahapedia_args(args: dict) -> dict:
    """Traduce query y faction al inglés para tools de Wahapedia."""
    out = dict(args)
    for key in ("query", "faction"):
        val = out.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = _translate_to_english(val)
    # Aplicar alias de facción (ej: ultramarines -> space-marines)
    faction = out.get("faction")
    if isinstance(faction, str):
        fn = faction.lower().strip().replace(" ", "-")
        if fn in _WAHAPEDIA_FACTION_ALIASES:
            out["faction"] = _WAHAPEDIA_FACTION_ALIASES[fn]
        else:
            # Normalizar guiones
            out["faction"] = fn.replace(" ", "-")
    return out


def _try_parse_tool_json(content: str) -> tuple[str, dict] | None:
    """
    Si el modelo devolvió JSON como texto en vez de tool_calls, extrae name y parameters.
    Ej: '{"name": "get_stratagems", "parameters": {"faction": "adeptus-custodes"}}'
    """
    content = content.strip()
    if "name" not in content or ("parameters" not in content and "arguments" not in content):
        return None
    # Buscar objeto JSON que empiece con {
    start = content.find("{")
    if start < 0:
        return None
    depth = 0
    for i, c in enumerate(content[start:], start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(content[start : i + 1])
                    if isinstance(obj, dict):
                        name = obj.get("name") or obj.get("tool")
                        params = obj.get("parameters") or obj.get("arguments") or {}
                        if name and isinstance(name, str):
                            return name, params if isinstance(params, dict) else {}
                except json.JSONDecodeError:
                    pass
                break
    return None


def _normalize_arguments(args) -> dict:
    """Ollama a veces devuelve arguments como string JSON; normaliza a dict."""
    if args is None:
        return {}
    if isinstance(args, dict):
        return args
    if isinstance(args, str) and args.strip():
        try:
            return json.loads(args)
        except json.JSONDecodeError:
            return {}
    return {}


def _msg_to_dict(msg) -> dict:
    """Convierte Message a dict para añadir a messages."""
    d = {"role": getattr(msg, "role", "assistant"), "content": getattr(msg, "content", "") or ""}
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        d["tool_calls"] = [
            {
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": _normalize_arguments(getattr(tc.function, "arguments", None)),
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def _run_mcp_command(parts: list[str]) -> str:
    """Ejecuta /mcp list o /mcp <name> disabled|enabled."""
    if len(parts) == 2 and parts[1].lower() == "list":
        servers = get_mcp_servers_raw()
        if not servers:
            return "[dim]No hay servidores MCP en .aia/mcp.json[/]"
        # Filtrar según modo activo
        if _active_mode:
            active = [s for s in servers if server_in_modo(s, _active_mode)]
            ctx_label = f"Modo {_active_mode.replace('modo_', '').replace('_', ' ').title()}"
        else:
            active = [s for s in servers if not s.get("modo")]
            ctx_label = "Modo general"
        if not active:
            return f"[dim]No hay MCPs para {ctx_label}[/]"
        lines = []
        for s in active:
            enabled = s.get("enabled") is not False
            icon = "🟢" if enabled else "🔴"
            name = s.get("name", "?")
            typ = "HTTP" if s.get("url") else "stdio"
            url_or_cmd = s.get("url") or f"{s.get('command', '')} {' '.join(str(a) for a in s.get('args', []))}"
            kw = s.get("keywords", [])
            kw_str = ", ".join(kw[:5]) + ("..." if len(kw) > 5 else "") if kw else "-"
            status = "" if enabled else " [dim](disabled)[/]"
            lines.append(f"  {icon} {name}{status}\n    tipo: {typ}\n    {url_or_cmd}\n    keywords: {kw_str}")
        return f"MCPs ({ctx_label}):\n\n" + "\n\n".join(lines)

    if len(parts) == 3:
        name, action = parts[1], parts[2].lower()
        if action in ("disabled", "disable"):
            if set_mcp_server_enabled(name, False):
                invalidate_mcp_cache()
                return f"[dim]{name} deshabilitado. No se considerará en clasificación.[/]"
            return f"[dim red]No existe servidor '{name}'[/]"
        if action in ("enabled", "enable"):
            if set_mcp_server_enabled(name, True):
                invalidate_mcp_cache()
                return f"[dim]{name} habilitado.[/]"
            return f"[dim red]No existe servidor '{name}'[/]"

    return "[dim]Uso: /mcp list | /mcp <name> disabled|enabled[/]"


# Modo activo: None = general, "modo_warhammer" = warhammer, "modo_monitor" = monitor
_active_mode: str | None = None


def _get_mod_config(mode_key: str | None = None) -> dict | None:
    """Config del modo desde mods.json (por key como 'modo_warhammer'). None si no existe."""
    key = mode_key if mode_key is not None else _active_mode
    if not key:
        return None
    for m in get_mods_raw():
        if m.get("key") == key:
            return m
    return None


def _run_mod_command(parts: list[str]) -> str:
    """Ejecuta /mod list | /mod <name> disabled|enabled."""
    sub = parts[1].lower() if len(parts) >= 2 else ""

    if not sub or sub == "list":
        mods = get_mods_raw()
        if not mods:
            return "[dim]No hay modos en .aia/mods.json[/]"
        lines = []
        for m in mods:
            name = m.get("name", "?")
            key = m.get("key", f"modo_{name}")
            color = m.get("color", "#ff8700")
            enabled = m.get("enabled") is not False
            status = "enabled" if enabled else "disabled"
            cmds_list = m.get("slashCommands", [])
            cmds_str = ", ".join(cmds_list) if cmds_list else "-"
            lines.append(f"  {name}  [{status}]\n    key: {key} | color: {color}\n    commands: {cmds_str}")
        return "Modos disponibles:\n\n" + "\n\n".join(lines)

    if len(parts) == 3:
        name, action = parts[1], parts[2].lower()
        if action in ("disabled", "disable"):
            if set_mod_enabled(name, False):
                invalidate_mcp_cache()
                return f"[dim]Modo '{name}' deshabilitado.[/]"
            return f"[dim red]No existe modo '{name}' en .aia/mods.json[/]"
        if action in ("enabled", "enable"):
            if set_mod_enabled(name, True):
                invalidate_mcp_cache()
                return f"[dim]Modo '{name}' habilitado.[/]"
            return f"[dim red]No existe modo '{name}' en .aia/mods.json[/]"

    return "[dim]Uso: /mod list | /mod <name> | /mod <name> disabled|enabled[/]"

# Historial de conversación (se mantiene entre llamadas a process())
_conversation_history: list[dict] = []

# Acción pendiente del live monitor (set en executor thread, leído en event loop)
_pending_live_action: str | None = None  # "start" | "stop"
_pending_feedback: dict | None = None   # {question, plan, response, mode}
_feedback_voted: str | None = None      # "up" | "down" | None



def _get_available_modes() -> list[str]:
    """Modos habilitados desde mods.json (fallback: campo modo_ en mcp.json)."""
    mods = get_mods_raw()
    if mods:
        return sorted(
            m.get("name", "") for m in mods
            if m.get("name") and m.get("enabled") is not False
        )
    # Fallback: leer modos de mcp.json (compatible con proyectos sin mods.json)
    servers = get_mcp_servers_raw()
    modos = set()
    for s in servers:
        raw = s.get("modo", "")
        if not raw:
            continue
        for m in raw.split(","):
            m = m.strip()
            if m.startswith("modo_"):
                modos.add(m.replace("modo_", "", 1))
    return sorted(modos)


def _get_all_slash_commands() -> list[str]:
    """Todos los comandos slash disponibles (para filtrar por aproximación)."""
    modes = _get_available_modes()
    cmds = ["/mcp list", "/mod list", "/cache delete", "/flush all", "/flush ollama", "/flush cache", "/flush history"]
    if _active_mode:
        cmds.insert(0, "/help")
        mod = _get_mod_config()
        if mod:
            for cmd in reversed(mod.get("slashCommands", [])):
                cmds.insert(0, cmd)
    return cmds + [f"/mod {m}" for m in modes]


def _get_slash_completions(prefix: str) -> list[str]:
    """Comandos que coinciden con el prefijo (ej: /cac -> /cache delete)."""
    prefix_lower = prefix.lower()
    return [cmd for cmd in _get_all_slash_commands() if cmd.lower().startswith(prefix_lower)]


class _SlashCompleter(Completer):
    """Sugiere comandos / con filtro por aproximación desde la primera letra."""

    def get_completions(self, document: Document, complete_event) -> None:
        text = document.text
        if not text.startswith("/"):
            return
        for cmd in _get_slash_completions(text):
            yield Completion(cmd, start_position=-len(text))


def _get_servers_by_mode(servers: list, mode: str, as_list: bool = False) -> list:
    """MCPs que tienen modo igual al indicado. Soporta modo coma-separado.
    as_list=True devuelve objetos completos (para clasificación); False devuelve nombres."""
    filtered = [s for s in servers if server_in_modo(s, mode) and s.get("name")]
    if as_list:
        return filtered
    return [s["name"] for s in filtered]


def _get_servers_for_general_mode(servers: list) -> list:
    """MCPs sin modo o con modo='ALL': disponibles en modo general."""
    return [s for s in servers if not s.get("modo") or s.get("modo") == "ALL"]


def _get_global_servers(servers: list) -> list:
    """MCPs con modo='ALL' o global=true: disponibles en todos los modos."""
    return [s for s in servers if (s.get("modo") == "ALL" or s.get("global")) and s.get("name")]


def _keyword_fallback(message: str, servers: list) -> list[str]:
    """
    Si el clasificador devolvió [], intenta matchear por keywords.
    Retorna servidores cuando el mensaje tiene 1+ keyword de ese servidor.
    """
    msg_lower = message.lower()
    best: list[tuple[int, str]] = []
    for s in servers:
        name = s.get("name")
        if not name:
            continue
        kw = s.get("keywords", [])
        if not isinstance(kw, list):
            continue
        matches = sum(1 for k in kw if isinstance(k, str) and k.lower() in msg_lower)
        if matches >= 1:
            best.append((matches, name))
    if not best:
        return []
    best.sort(reverse=True, key=lambda x: x[0])
    return [name for _, name in best]


_MAX_TURNS = 10


def _count_turns(history: list[dict]) -> int:
    """Cuenta el número de turnos (mensajes de usuario) en el historial."""
    return sum(1 for m in history if m.get("role") == "user")


def _compress_history(history: list[dict], phase: dict[str, str] | None) -> list[dict]:
    """
    Cuando el historial supera _MAX_TURNS, resume los turnos más antiguos con el modelo
    y retorna un historial comprimido. Muestra 'Resumiendo Conversación' en el spinner
    con un mínimo de 1 segundo en pantalla.
    """
    _agil_emit("COMPRESS", f"history turns={_count_turns(history)}")
    # Agrupar mensajes en turnos (cada turno empieza con role=user)
    turns: list[list[dict]] = []
    current: list[dict] = []
    for msg in history:
        if msg.get("role") == "user" and current:
            turns.append(current)
            current = [msg]
        else:
            current.append(msg)
    if current:
        turns.append(current)

    if len(turns) <= _MAX_TURNS:
        return history

    old_turns = turns[:-_MAX_TURNS]
    recent_turns = turns[-_MAX_TURNS:]
    old_messages = [m for turn in old_turns for m in turn]
    recent_messages = [m for turn in recent_turns for m in turn]

    # Señalizar estado en GUI y registrar tiempo de inicio
    if phase is not None:
        phase["value"] = "Resumiendo Conversación"
    start = time.monotonic()

    try:
        lines = []
        for m in old_messages:
            role = m.get("role", "")
            content = m.get("content", "") or ""
            if role == "user" and content:
                lines.append(f"Usuario: {content}")
            elif role == "assistant" and content:
                lines.append(f"Asistente: {content}")
            elif role == "tool" and content:
                snippet = content[:200] + "..." if len(content) > 200 else content
                lines.append(f"[Herramienta]: {snippet}")

        r = llm_chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Resume brevemente (máximo 4 oraciones en español) esta conversación previa, "
                        "destacando los datos importantes mencionados:\n\n" + "\n".join(lines)
                    ),
                }
            ],
            purpose="compress_context",
            options=_OLLAMA_OPTIONS,
        )
        summary = (getattr(r.message, "content", None) or "").strip() or "Conversación previa resumida."
    except Exception:
        summary = "Conversación previa resumida."

    # Garantizar mínimo 1 segundo visible en el GUI
    elapsed = time.monotonic() - start
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)

    return [
        {"role": "user", "content": f"[Resumen de conversación anterior]: {summary}"},
        {"role": "assistant", "content": "Entendido, tengo en cuenta el contexto anterior."},
    ] + recent_messages


def _fmt_tool_call(server_name: str | None, tool_name: str, args: dict) -> str:
    """Formatea una llamada MCP para el log: 'http>>mcp.server.tool(k=v, ...)'."""
    proto = get_server_transport(server_name) if server_name else "sh"
    srv = server_name or "?"
    params = ", ".join(f"{k}={repr(v)}" for k, v in args.items()) if args else ""
    return f"{proto}>>mcp.{srv}.{tool_name}({params})"


def _think(phase: dict, entry: str) -> None:
    """Append al canal think_log (pensamiento) en vez de log (pasos)."""
    phase.setdefault("think_log", []).append(entry)


def _plan_execution(message: str, mcp_tools: list, phase: dict) -> None:
    """Pensamiento: COAGITATOR_MODEL genera los pasos, cada uno se registra en sequential-thinking
    y se emite al canal pensamiento paso a paso.
    """
    _agil_emit("PLAN_EXEC", f"tools={len(mcp_tools)} msg={message[:60]!r}")
    try:
        phase["value"] = "Planificando"

        # ── Cache HIT ──────────────────────────────────────────────────
        cached = plan_cache_get(message)
        if cached:
            _agil_emit("PLAN_CACHE_HIT", f"msg={message[:60]!r}")
            for entry in cached.split("\n"):
                if entry:
                    _think(phase, entry)
            _think(phase, "🎯 CACHE HIT")
            return

        all_servers = get_mcp_servers()
        st_server = next(
            (s for s in all_servers if s.get("name") == "sequential-thinking" and s.get("enabled", True)),
            None,
        )

        if not st_server:
            _plan_execution_llm(message, mcp_tools, phase)
            return

        # Lista de tools para el planificador
        tool_names = [t.get("function", {}).get("name", "") for t in mcp_tools if t.get("function", {}).get("name")]
        tools_list = ", ".join(tool_names) if tool_names else "ninguna"

        # COAGITATOR_MODEL genera los pasos del plan
        steps_response = llm_chat(
            model=COAGITATOR_MODEL,
            options=_OLLAMA_OPTIONS,
            purpose="plan_steps",
            messages=[
                {"role": "system", "content": (
                    "Eres un planificador. Dado un prompt y las tools MCP disponibles, "
                    "lista los pasos de ejecución. Un paso por línea, sin numeración ni viñetas.\n"
                    "Formato de paso con tool: mcp.<tool>(param=valor)\n"
                    "Último paso siempre: LLM responde al usuario\n"
                    "Solo los pasos, sin texto adicional. Máximo 5 pasos."
                )},
                {"role": "user", "content": f"Tools disponibles: {tools_list}\n\nPregunta: {message}"},
            ],
        )
        raw = (getattr(steps_response.message, "content", None) or "").strip()
        steps = [s.strip().lstrip("-•*0123456789.) ") for s in raw.split("\n") if s.strip()][:5]

        if not steps:
            steps = ["LLM responde al usuario"]

        # Reemplazar "mcp.toolname(" por "servidor.toolname(" en cada paso
        import re as _re
        def _resolve_step(s: str) -> str:
            def _repl(m):
                tool = m.group(1)
                srv = get_server_name_for_tool(tool) or "mcp"
                return f"{srv}.{tool}("
            return _re.sub(r"mcp\.([\w-]+)\(", _repl, s)
        steps = [_resolve_step(s) for s in steps]

        # Registrar cada paso en sequential-thinking y emitir al canal pensamiento
        total = len(steps)
        last_result = ""
        think_entries: list[str] = []
        for i, step in enumerate(steps):
            last_result = call_tool_on_server(st_server, "sequentialthinking", {
                "thought": step,
                "thoughtNumber": i + 1,
                "totalThoughts": total,
                "nextThoughtNeeded": i < total - 1,
            })
            entry = f"PENSAMIENTO {i + 1}/{total}>> {step}"
            _think(phase, entry)
            think_entries.append(entry)

        seq_entry = ""
        if last_result and last_result.strip():
            seq_entry = f"SEQUENTIAL>> {last_result.strip()}"
            _think(phase, seq_entry)
            think_entries.append(seq_entry)

        # ── Guardar en cache ───────────────────────────────────────────
        plan_cache_set(message, "\n".join(think_entries))

    except Exception as e:
        logger.debug("_plan_execution error: %s", e)


def _plan_execution_llm(message: str, mcp_tools: list, phase: dict) -> None:
    """Fallback sin sequential-thinking: emite tools disponibles como plan al pensamiento."""
    _agil_emit("PLAN_EXEC_LLM", f"msg={message[:60]!r}")
    tool_names = [t.get("function", {}).get("name", "") for t in mcp_tools if t.get("function", {}).get("name")]
    if tool_names:
        plan = " -> ".join(tool_names[:6]) + (" -> …" if len(tool_names) > 6 else "")
        _think(phase, f"PENSAMIENTO 1/1>> {plan}")
    else:
        _think(phase, "PENSAMIENTO 1/1>> LLM responde al usuario")


def process(message: str, phase: dict[str, str] | None = None) -> str:
    """Envía el mensaje a Ollama con tools y devuelve la respuesta."""
    global _active_mode, _conversation_history, _pending_live_action
    clear_interrupt()  # reset al inicio de cada proceso
    msg_stripped = message.strip()
    msg_lower = msg_stripped.lower()

    # Comandos slash: /mod
    if msg_lower.startswith("/mod"):
        parts = msg_stripped.split()
        sub = parts[1].lower() if len(parts) >= 2 else ""

        # /mod list o /mod sin args → listar modos
        if not sub or sub == "list":
            return _run_mod_command(parts)

        # /mod <name> disabled|enabled → toggle
        if len(parts) == 3 and parts[2].lower() in ("disabled", "disable", "enabled", "enable"):
            return _run_mod_command(parts)

        # /mod <name> → activar modo
        available_modes = _get_available_modes()
        mode_name = sub.replace(" ", "_")
        mode_key = f"modo_{mode_name}" if not mode_name.startswith("modo_") else mode_name
        if mode_key.replace("modo_", "", 1) in available_modes:
            _active_mode = mode_key
            _conversation_history.clear()
            invalidate_mcp_cache()
            label = mode_key.replace("modo_", "", 1).replace("_", " ").title()
            return f"[dim]Modo {label} activado. Escribe 'exit' o presiona ⎋ Esc para salir.[/]"
        import difflib
        close = difflib.get_close_matches(mode_name, available_modes, n=1, cutoff=0.6)
        if close:
            _active_mode = f"modo_{close[0]}"
            _conversation_history.clear()
            invalidate_mcp_cache()
            label = close[0].replace("_", " ").title()
            return f"[dim]Modo {label} activado. Escribe 'exit' o presiona ⎋ Esc para salir.[/]"
        return f"[dim]Modo '{sub}' no existe. Modos: {', '.join(available_modes)}[/]"

    if msg_lower == "/resume":
        return "__resume__"

    if msg_lower == "/help":
        if not _active_mode:
            return (
                "[bold]AiA — ¿Qué podés preguntarme?[/bold]\n\n"
                "[bold]⏰  Hora y fecha[/bold]\n"
                '  "¿Qué hora es?"\n'
                '  "¿Qué día es hoy?"\n'
                '  "¿Cuántos días faltan para el viernes?"\n\n'
                "[bold]🌡️  Clima[/bold]\n"
                '  "¿Qué temperatura hay en Santiago?"\n'
                '  "¿Cómo está el tiempo en Buenos Aires?"\n'
                '  "Pronóstico para los próximos 7 días en Valparaíso"\n\n'
                "[bold]⚔️  Warhammer 40K (modo warhammer)[/bold]\n"
                '  "Dame las facciones disponibles"\n'
                '  "Dame las unidades de los Necrons"\n'
                '  "Dame las estratagemas de los Space Marines"\n'
                '  "Estadísticas de un Rhino"\n'
                '  "Datos de Saint Celestine"\n\n'
                "[bold]💬  Conversación general[/bold]\n"
                '  "Explícame cómo funciona el protocolo MQTT"\n'
                '  "Resume este texto: ..."\n'
                '  "Traduce al inglés: ..."\n'
                '  "¿Cuál es la diferencia entre X e Y?"\n\n'
                "[bold]Modos disponibles:[/bold]\n"
                "  [dim]/mod warhammer[/dim]  estadísticas y lore de Warhammer 40K\n"
                "  [dim]/mod monitor[/dim]    nivel del estanque en tiempo real\n"
                "  [dim]/mod dev[/dim]        asistente de programación\n"
                "  [dim]/mod airbnb[/dim]     gestión de reservas y finanzas\n"
                "  [dim]/mod list[/dim]       ver todos los modos\n"
            )
        return get_mode_help(_active_mode)

    if msg_lower == "/cache delete":
        cache_delete_all()
        plan_cache_delete_all()
        invalidate_mcp_cache()
        _conversation_history.clear()
        return "[dim]Cache borrada (clasificador + planificador + MCP tools + historial de conversación).[/]"

    if msg_lower.startswith("/flush"):
        subcmd = msg_lower[len("/flush"):].strip()

        def _flush_ollama() -> str:
            from ollama import ps as ollama_ps
            loaded = ollama_ps().models or []
            unloaded = []
            for m in loaded:
                name = m.model or m.name
                if name:
                    llm_generate(model=name, prompt="", keep_alive=0)
                    unloaded.append(name)
            if not unloaded:
                llm_generate(model=OLLAMA_MODEL, prompt="", keep_alive=0)
                unloaded = [OLLAMA_MODEL]
            return f"Ollama descargado ({', '.join(unloaded)})."

        def _flush_cache() -> str:
            cache_delete_all()
            plan_cache_delete_all()
            invalidate_mcp_cache()
            return "Cache borrada (clasificador + planificador + MCP tools)."

        def _flush_history() -> str:
            _conversation_history.clear()
            return "Historial de conversación borrado."

        if subcmd == "ollama":
            try:
                return f"[dim]{_flush_ollama()}[/]"
            except Exception as e:
                return f"[dim red]Error al descargar Ollama: {e}[/]"
        elif subcmd == "cache":
            return f"[dim]{_flush_cache()}[/]"
        elif subcmd == "history":
            return f"[dim]{_flush_history()}[/]"
        elif subcmd == "all":
            msgs = [_flush_cache(), _flush_history()]
            try:
                msgs.append(_flush_ollama())
            except Exception as e:
                msgs.append(f"Error al descargar Ollama: {e}")
            return "[dim]" + " ".join(msgs) + "[/]"
        else:
            return "[dim]Uso: /flush all | /flush ollama | /flush cache | /flush history[/]"

    if msg_lower.startswith("/mcp"):
        parts = msg_stripped.split()
        return _run_mcp_command(parts)

    # Comandos slash definidos en mods.json (solo válidos en el modo que los define)
    if msg_stripped.startswith("/") and _active_mode:
        mod_cfg = _get_mod_config()
        mod_commands = mod_cfg.get("commands", {}) if mod_cfg else {}
        if msg_stripped in mod_commands:
            cmd_def = mod_commands[msg_stripped]
            # Formato string: solo shell, muestra output directo
            # Formato objeto: {"shell": "...", "prompt": "..."} → shell + LLM con output
            shell_cmd = cmd_def if isinstance(cmd_def, str) else cmd_def.get("shell", "")
            llm_prompt = None if isinstance(cmd_def, str) else cmd_def.get("prompt")
            cwd = _project_root()
            try:
                result = subprocess.run(
                    shell_cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=60
                )
                output = result.stdout
                if result.stderr:
                    output += f"\n[stderr]\n{result.stderr}"
                if result.returncode != 0:
                    output += f"\n[exit: {result.returncode}]"
                output = output.strip() or "(sin salida)"
            except subprocess.TimeoutExpired:
                return "[dim red]Timeout: el comando tardó más de 60s[/]\n"
            except Exception as e:
                return f"[dim red]Error: {e}[/]\n"

            if llm_prompt:
                # Delegar al LLM con el output inyectado en el prompt
                return process(llm_prompt.replace("{output}", output), phase=phase)
            return output + "\n"

    # Bypass: consultas de hora/fecha solo necesitan get_time (builtin), no MCP
    _time_keywords = ("hora", "fecha", "qué hora", "dime la hora", "qué día", "qué fecha")
    if any(k in msg_lower for k in _time_keywords):
        selected = []
        servers = []
    else:
        selected = None
        servers = get_mcp_servers()

    server_names = [s["name"] for s in servers if s.get("name")]

    if servers:
        # Pool de servidores según el modo
        global_servers = _get_global_servers(servers)
        if _active_mode:
            mode_servers = _get_servers_by_mode(servers, _active_mode, as_list=True)
            mode_names = {s["name"] for s in mode_servers}
            pool = mode_servers + [s for s in global_servers if s["name"] not in mode_names]
            cache_key = f"{_active_mode}:{message}"
        else:
            general_servers = _get_servers_for_general_mode(servers)
            general_names = {s["name"] for s in general_servers}
            pool = general_servers + [s for s in global_servers if s["name"] not in general_names]
            cache_key = message

        # Clasificación con cache
        cached = cache_get(cache_key)
        if cached is not None:
            if phase is not None:
                phase["value"] = "Cacheando"  # noqa: B905
            selected = cached
        else:
            if phase is not None:
                phase["value"] = "Clasificando"  # noqa: B905
                phase.setdefault("log", []).append(f"Clasificación ?> LLM>>Ollama.{CLASSIFIER_MODEL}")  # noqa: B905
            _agil_emit("CLASSIFY_LLM", f"servers={len(pool)}")
            selected = classify_prompt(message, pool)
            cache_set(cache_key, selected)

        # Fallback por keywords si el clasificador devolvió vacío
        if not selected:
            selected = _keyword_fallback(message, pool)

    # Instalar hooks ANTES de cargar tools y lanzar el hilo de planificación,
    # para que cualquier llamada MCP/LLM dentro del hilo ya tenga los callbacks activos.
    def _hook_on_call(name: str, args: dict) -> None:
        srv = get_server_name_for_tool(name)
        if phase is not None:
            phase["value"] = f"mcp_exe@{srv}" if srv else "mcp_exe"
            phase.setdefault("mcp_log", []).append(_fmt_tool_call(srv, name, args))

    def _hook_on_result(name: str, result: str) -> None:
        if phase is not None:
            _r = result or ""
            phase.setdefault("mcp_log", []).append(f"RESULT>> {_r[:400]}{'…' if len(_r) > 400 else ''}")

    def _hook_on_llm_call(model: str, purpose: str, messages: list) -> None:
        if phase is not None:
            phase.setdefault("llm_log", []).append(
                f"CALL>> model={model} purpose={purpose!r} msgs={len(messages)}"
            )

    def _hook_on_llm_result(model: str, purpose: str, resp: object, elapsed_ms: float) -> None:
        if phase is not None:
            ec = getattr(resp, "eval_count", 0) or 0
            pc = getattr(resp, "prompt_eval_count", 0) or 0
            content = (getattr(getattr(resp, "message", None), "content", None) or "").strip()
            phase.setdefault("llm_log", []).append(
                f"RESULT>> model={model} purpose={purpose!r} "
                f"time={elapsed_ms:.0f}ms out={ec}tok ctx={pc}tok\n{content}"
            )

    set_tool_hooks(_hook_on_call, _hook_on_result)
    set_llm_hooks(_hook_on_llm_call, _hook_on_llm_result)
    _set_memory_hook(lambda op, d: phase.setdefault("memory_log", []).append(f"{op}>> {d}") if phase is not None else None)
    if phase is not None:
        _agil_install(phase)
        _agil_emit("PROCESS_START", f"msg={message[:80]!r} mode={_active_mode or 'general'}")

    # selected=None: builtin + todos los MCP. selected=[]: solo builtin.
    # selected=[...]: builtin + esos MCP. Siempre pasamos tools para que get_time funcione.
    tools = get_tools(selected)
    _agil_emit("TOOLS_LOAD", f"selected={selected} n={len(tools)}")

    # Detectar si MCP no se cargaron (conexión fallida)
    mcp_tools = [t for t in tools if isinstance(t, dict) and t.get("type") == "function"]
    mcp_load_failed = selected and len(selected) > 0 and len(mcp_tools) == 0
    logger.debug("process selected=%s mcp_tools=%s mcp_load_failed=%s", selected, [t.get("function",{}).get("name") for t in mcp_tools], mcp_load_failed)

    # Planificación en paralelo — se lanza AQUÍ, lo antes posible (hooks ya instalados,
    # tools ya conocidas). La compresión y el loop LLM corren mientras el plan avanza.
    if phase is not None:
        _mcp_tools_snapshot = list(mcp_tools)
        _plan_thread = _threading.Thread(
            target=_plan_execution,
            args=(message, _mcp_tools_snapshot, phase),
            daemon=True,
        )
        _plan_thread.start()
        phase["_plan_thread"] = _plan_thread  # para que agent_api espere antes de cerrar SSE

    # Comprimir historial si supera el límite de turnos
    if _count_turns(_conversation_history) >= _MAX_TURNS:
        _conversation_history = _compress_history(_conversation_history, phase)

    cwd = os.getcwd()
    system_prompt = _build_system_prompt(selected, tools, cwd)
    messages = [
        {"role": "system", "content": system_prompt},
    ] + _conversation_history + [
        {"role": "user", "content": message},
    ]

    try:
        last_tool_result = None
        pending_images: list[str] = []  # marcadores [AIA_IMG:...] acumulados de tool results
        _img_re = re.compile(r"\[AIA_IMG:[^\]]+\]")
        lang_hint = " (spanglish para WH40K)" if selected and "wahapedia" in selected else ""
        MAX_TOOL_ROUNDS = 8

        _files_read: list[str] = []  # paths leídos en modo_dev para AIA_FILE markers

        def _track_file_read(tool_name: str, tool_args: dict) -> None:
            """Registra archivos leídos en modo_dev para inyectar AIA_FILE markers."""
            if _active_mode != "modo_dev":
                return
            if tool_name in ("read_file", "get_file_contents", "read"):
                _p = tool_args.get("path") or tool_args.get("file_path", "")
                if _p and isinstance(_p, str) and _p not in _files_read:
                    _files_read.append(_p)
            elif tool_name == "read_multiple_files":
                for _p in (tool_args.get("paths") or []):
                    if isinstance(_p, str) and _p not in _files_read:
                        _files_read.append(_p)
            elif tool_name in ("run_command", "execute_command", "bash"):
                # Detectar: cat /path, head /path, tail /path
                cmd = tool_args.get("command") or tool_args.get("cmd") or ""
                if isinstance(cmd, str):
                    import shlex
                    try:
                        parts = shlex.split(cmd.strip())
                    except ValueError:
                        parts = cmd.strip().split()
                    if parts and parts[0] in ("cat", "head", "tail", "less", "bat"):
                        for part in parts[1:]:
                            if part and not part.startswith("-") and ("." in part or "/" in part):
                                _p = part if part.startswith("/") else str(Path(cwd) / part)
                                if _p not in _files_read:
                                    _files_read.append(_p)
                                break

        for _round in range(MAX_TOOL_ROUNDS):
            # Verificar interrupción antes de cada ronda
            if _interrupt_event.is_set():
                reason = _interrupt_reason or "user"
                if phase is not None:
                    phase.setdefault("log", []).append(f"Interrupted ?> {reason}")  # noqa: B905
                return f"__interrupted__:{reason}"

            # LLM con tools en cada ronda — permite múltiples llamadas secuenciales
            _agil_emit("LLM_ROUND", f"round={_round} tools={len(tools)} history={len(messages)}")
            if phase is not None:
                phase["value"] = "Generando Respuesta"  # noqa: B905
                phase.setdefault("log", []).append(f"Generando Respuesta ?> LLM>>Ollama.{OLLAMA_MODEL}")  # noqa: B905
            response = llm_chat(model=OLLAMA_MODEL, messages=messages, tools=tools, options=_OLLAMA_OPTIONS, purpose="chat")
            msg = response.message

            # Emitir métricas de Ollama al canal agilidad
            if phase is not None:
                try:
                    _ec = getattr(response, "eval_count", 0) or 0
                    _ed = getattr(response, "eval_duration", 0) or 0
                    _pc = getattr(response, "prompt_eval_count", 0) or 0
                    _pd = getattr(response, "prompt_eval_duration", 0) or 0
                    _ld = getattr(response, "load_duration", 0) or 0
                    _td = getattr(response, "total_duration", 0) or 0
                    _gen_tps  = round(_ec / (_ed / 1e9), 1) if _ed > 0 else 0
                    _pre_tps  = round(_pc / (_pd / 1e9), 1) if _pd > 0 else 0
                    _load_ms  = round(_ld / 1e6)
                    _total_ms = round(_td / 1e6)
                    _stats_line = (
                        f"gen={_gen_tps}tok/s | prefill={_pre_tps}tok/s | "
                        f"load={_load_ms}ms | total={_total_ms}ms | "
                        f"out={_ec}tok | ctx={_pc}tok"
                    )
                    phase.setdefault("agilidad", []).append(f"OLLAMA_STATS>> {_stats_line}")  # noqa: B905
                except Exception:
                    pass

            if hasattr(msg, "tool_calls") and msg.tool_calls:
                # Ejecutar todas las tool_calls de esta ronda
                _agil_emit("TOOL_CALLS", f"round={_round} count={len(msg.tool_calls)} names={[tc.function.name for tc in msg.tool_calls]}")
                logger.debug("tool_calls round=%d count=%d names=%s", _round, len(msg.tool_calls), [tc.function.name for tc in msg.tool_calls])
                messages.append(_msg_to_dict(msg))
                for tc in msg.tool_calls:
                    name = tc.function.name
                    if name == "list_mcp_databases":
                        name = "list_databases"
                    args = _normalize_arguments(getattr(tc.function, "arguments", None))
                    if name in ("list_databases", "list-databases") and args:
                        args = {}
                    if args.get("path") in (".", "./", ""):
                        args["path"] = cwd
                    if selected and len(selected) > 0 and get_server_name_for_tool(name) == "wahapedia" and args:
                        args = _translate_wahapedia_args(args)
                    # El log se emite desde execute_tool vía _hook_on_call/_hook_on_result
                    result = execute_tool(name, args)
                    _track_file_read(name, args)
                    last_tool_result = result
                    pending_images.extend(_img_re.findall(result))
                    messages.append({"role": "tool", "tool_name": name, "content": result})
                    if name == "start_live_monitor":
                        _pending_live_action = "start"
                    elif name == "stop_live_monitor":
                        _pending_live_action = "stop"
                # Continuar el loop para que el LLM procese los resultados
                continue

            # Sin tool_calls: revisar fallback JSON en texto
            content = (getattr(msg, "content", None) or "").strip()
            tool_parsed = _try_parse_tool_json(content)
            if tool_parsed:
                name, params = tool_parsed
                if name == "list_mcp_databases":
                    name = "list_databases"
                if name in ("list_databases", "list-databases") and params:
                    params = {}
                if selected and len(selected) > 0 and get_server_name_for_tool(name) == "wahapedia" and params:
                    params = _translate_wahapedia_args(params)
                # El log se emite desde execute_tool vía _hook_on_call/_hook_on_result
                result = execute_tool(name, params)
                _track_file_read(name, params)
                last_tool_result = result
                pending_images.extend(_img_re.findall(result))
                if name == "start_live_monitor":
                    _pending_live_action = "start"
                elif name == "stop_live_monitor":
                    _pending_live_action = "stop"
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"Resultado de {name}: {result}\n\nContinúa respondiendo la pregunta del usuario en español{lang_hint}."})
                continue

            # Respuesta final en texto plano — fin determinista del loop
            if content:
                # En modo_dev: inyectar markers de archivo para que el frontend los capture
                logger.debug("modo_dev _files_read=%s", _files_read)
                if _active_mode == "modo_dev" and _files_read:
                    markers = " ".join(f"[AIA_FILE:{p}]" for p in _files_read)
                    content = markers + "\n" + content
                    logger.debug("AIA_FILE markers injected: %s", markers)
                if mcp_load_failed:
                    content += "\n\n[dim]Nota: No se cargaron las herramientas MCP. ¿Están los servidores corriendo? (ej: cd aia-mcp && poetry run mcp all --http). Prueba /cache delete si el clasificador falló.[/]"
                if pending_images:
                    new_imgs = [img for img in pending_images if img not in content]
                    if new_imgs:
                        content = "\n".join(new_imgs) + "\n" + content
                clean = [
                    m for m in messages[1:]
                    if m.get("role") in ("user", "assistant")
                    and not m.get("tool_calls")
                    and m.get("content")
                ]
                _conversation_history = clean + [{"role": "assistant", "content": content}]
                _history_mod.save(_active_mode, _conversation_history)
                _agil_emit("PROCESS_END", f"rounds={_round} result_len={len(content)}")
                _agil_uninstall()
                return content
            break

        # Agotadas las rondas o sin contenido
        if last_tool_result:
            clean = [
                m for m in messages[1:]
                if m.get("role") in ("user", "assistant")
                and not m.get("tool_calls")
                and m.get("content")
            ]
            _conversation_history = clean + [{"role": "assistant", "content": last_tool_result}]
            _history_mod.save(_active_mode, _conversation_history)
            _agil_emit("PROCESS_END", f"rounds={_round} result_len={len(last_tool_result)}")
            _agil_uninstall()
            return last_tool_result
        return "[dim]Sin respuesta.[/]"

    except Exception as e:
        return f"[dim red]Error: {e}\n¿Ollama está corriendo? (ollama serve)[/]"


def _get_output_width() -> int:
    """Ancho del área de salida para extender el fondo de las preguntas (estilo Claude)."""
    try:
        from prompt_toolkit.application.current import get_app
        return get_app().output.get_size().columns
    except Exception:
        try:
            import shutil
            return shutil.get_terminal_size().columns
        except Exception:
            return 80


class _QuestionHighlightLexer(Lexer):
    """Resalta las preguntas del usuario con fondo oscuro y texto blanco (estilo Claude)."""

    def lex_document(self, document: Document):
        lines = document.lines

        def get_line(lineno: int):
            try:
                line = lines[lineno]
                if line.lstrip().startswith("›"):
                    width = _get_output_width()
                    padded = line + " " * max(0, width - len(line) - 1)
                    return [("bg:#2d2d2d fg:white", padded)]
                # Línea de spinner: empieza con carácter braille
                if line and line[0] in "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏":
                    bright, dim = _get_banner_colors()
                    # Ícono braille: color banner completo + bold
                    parts = [("bold fg:" + bright, line[0])]
                    highlight_next = False
                    for c in line[1:]:
                        if c == ZW:
                            highlight_next = True
                        elif highlight_next:
                            parts.append(("bold fg:" + bright, c))
                            highlight_next = False
                        else:
                            parts.append(("fg:" + dim, c))
                    return parts if parts else [("fg:" + dim, line)]
                return [("", line)]
            except IndexError:
                return []

        return get_line


# Spinner: mismos caracteres braille que Ollama CLI (progress/spinner.go)
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
ZW = "\u200b"  # Zero-width space para marcar la letra resaltada


def _get_banner_colors() -> tuple[str, str]:
    """Retorna (color_brillante, color_tenue) del banner según el modo activo (desde mods.json)."""
    mod = _get_mod_config()
    if mod:
        return mod.get("color", "#ff8700"), mod.get("colorDim", "#804400")
    return "#ff8700", "#804400"


def _scroll_output(output_buffer: Buffer) -> None:
    """Scroll al final para ver lo último. Si el contenido cabe en pantalla,
    prompt_toolkit muestra desde el top automáticamente."""
    output_buffer.cursor_position = len(output_buffer.text)


def run():
    """Loop principal del agente."""
    history_path = _project_root() / ".aia" / "conversation_history"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    input_history = FileHistory(str(history_path))
    slash_completer = _SlashCompleter()
    input_buffer = Buffer(
        name="input",
        multiline=False,
        history=input_history,
        completer=slash_completer,
        complete_while_typing=True,
        enable_history_search=True,
    )
    output_buffer = Buffer(name="output")
    output_control = _ScrollableBufferControl(
        buffer=output_buffer,
        lexer=_QuestionHighlightLexer(),
        focusable=True,
        focus_on_click=False,
    )
    output_text_area = Window(
        content=output_control,
        wrap_lines=True,
        # NOTE: output_control._window se inyecta justo abajo
        right_margins=[ScrollbarMargin(display_arrows=True)],
    )
    output_control._window = output_text_area  # inyectar referencia para scroll

    def _display_iterm2_image(path: str) -> None:
        """Muestra una imagen PNG inline via protocolo iTerm2 escribiendo a /dev/tty."""
        logger.debug("iterm2_image: path=%s", path)
        try:
            import base64 as _b64
            with open(path, "rb") as f:
                data = _b64.b64encode(f.read()).decode()
            name = os.path.basename(path)
            seq = f"\033]1337;File=name={name};inline=1;width=100%:{data}\007\n"
            logger.debug("iterm2_image: seq_len=%d writing to /dev/tty", len(seq))
            with open("/dev/tty", "wb") as tty:
                tty.write(seq.encode())
            logger.debug("iterm2_image: done")
        except Exception as e:
            logger.error("iterm2_image error: %s", e)

    _AIA_IMG_RE = re.compile(r"\[AIA_IMG:([^\]]+)\]")
    _pending_display_images: list[str] = []

    def append_output(text: str) -> None:
        images = _AIA_IMG_RE.findall(text)
        if images:
            _pending_display_images.extend(img.strip() for img in images)
            text = _AIA_IMG_RE.sub("", text).strip()
            if not text:
                output_buffer.cursor_position = len(output_buffer.text)
                _scroll_output(output_buffer)
                return
        output_buffer.cursor_position = len(output_buffer.text)
        output_buffer.insert_text(text)
        _scroll_output(output_buffer)

    def on_accept(buff: Buffer) -> bool:
        global _active_mode, _conversation_history
        text = buff.text.strip()
        buff.reset()
        app = get_app()

        if not text:
            return True
        if text.lower() in ("exit", "quit"):
            app.exit(result=None)
            return True
        # Guardar en historial (flecha arriba) para mensajes válidos
        if text and text != "?":
            input_history.append_string(text)
        if text == "?":
            append_output("exit | quit - salir | ! <cmd> - shell | /mod list | /mod <name> | /mod <name> disabled|enabled | /cache delete | /flush all|ollama|cache|history | /mcp list | /mcp <name> disabled|enabled\n")
            app.invalidate()
            return True

        # /watch: monitor en vivo por MQTT (solo en modo_monitor)
        if text.lower() == "/watch":
            if _active_mode != "modo_monitor":
                append_output("El monitor en vivo solo esta disponible en modo monitor (/modo monitor).\n\n")
            elif live_monitor.is_active():
                live_monitor.stop()
                append_output("Monitor en vivo detenido.\n\n")
            else:
                try:
                    _loop = asyncio.get_running_loop()
                except RuntimeError:
                    _loop = asyncio.get_event_loop()
                err = live_monitor.start(append_output, app.invalidate, _loop)
                if err:
                    append_output(f"{err}\n\n")
                else:
                    topic = os.environ.get("MQTT_TOPIC_OUT", "MQTT")
                    append_output(f"Monitor en vivo  {topic}\nEscribe /watch para detener.\n\n")
            app.invalidate()
            return True

        # ! <cmd>: ejecutar comando de shell directamente (no interactivo)
        if text.startswith("!"):
            cmd = text[1:].strip()
            if not cmd:
                append_output("Uso: ! <comando>  (ej: ! ls -la)\n\n")
                app.invalidate()
                return True
            _interactive = ("vim", "vi", "nano", "less", "more", "top", "htop",
                            "man", "watch", "ssh", "ftp", "python", "ipython",
                            "bash", "zsh", "sh", "fish")
            first_word = cmd.split()[0].split("/")[-1]
            if first_word in _interactive:
                append_output(f"'{first_word}' es interactivo y no puede correr aquí.\n\n")
                app.invalidate()
                return True
            append_output("› " + text + "\n")
            app.invalidate()
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30
                )
                out = result.stdout
                err = result.stderr
                if out:
                    append_output(out if out.endswith("\n") else out + "\n")
                if err:
                    append_output(err if err.endswith("\n") else err + "\n")
                if not out and not err:
                    append_output(f"[exit {result.returncode}]\n")
            except subprocess.TimeoutExpired:
                append_output("Timeout (30s).\n")
            except Exception as e:
                append_output(f"Error: {e}\n")
            append_output("\n")
            app.invalidate()
            return True

        # Si el live monitor está activo y el usuario envía cualquier otro comando, detenerlo
        if live_monitor.is_active():
            live_monitor.stop()
            append_output("Monitor en vivo detenido.\n")

        phase = {"value": "Clasificando"}
        append_output("› " + text + "\n")
        append_output(SPINNER_FRAMES[0] + " Clasificando...\n")
        app.invalidate()

        spinner_task = None

        def get_spinner_label():
            return phase.get("value", "Pensando")

        async def spinner_loop():
            nonlocal spinner_task
            i = 1
            try:
                while True:
                    # Flush de líneas de log MCP pendientes (tool calls)
                    pending = phase.pop("log", None) if isinstance(phase.get("log"), list) else None
                    if pending:
                        lines = output_buffer.text.rsplit("\n", 2)
                        prefix = lines[0] if lines else ""
                        log_text = "\n".join(f"  {l}" for l in pending)
                        output_buffer.text = prefix + "\n" + log_text + "\n\n"
                        _scroll_output(output_buffer)

                    lines = output_buffer.text.rsplit("\n", 2)
                    if len(lines) >= 2:
                        frame = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
                        label = get_spinner_label()
                        idx = i % len(label) if label else 0
                        animated = label[:idx] + ZW + label[idx:] if label else ""
                        output_buffer.text = lines[0] + "\n" + frame + " " + animated + "...\n"
                        _scroll_output(output_buffer)
                        app.invalidate()
                    i += 1
                    await asyncio.sleep(0.1)  # 100ms como Ollama
            except asyncio.CancelledError:
                pass

        def update_ui(result: str):
            global _pending_live_action, _pending_feedback, _feedback_voted
            nonlocal spinner_task
            if spinner_task and not spinner_task.done():
                spinner_task.cancel()
            lines = output_buffer.text.rsplit("\n", 2)
            output_buffer.text = (lines[0] if lines else "") + "\n\n"
            append_output(result + "\n\n")
            # Disparar acción de live monitor si el modelo llamó start/stop_live_monitor
            action = _pending_live_action
            _pending_live_action = None
            if action == "start" and not live_monitor.is_active():
                live_monitor.start(append_output, app.invalidate, loop)
            elif action == "stop" and live_monitor.is_active():
                live_monitor.stop()
            # Activar feedback bar para la respuesta recién mostrada
            _feedback_voted = None
            _pending_feedback = {
                "question": text,
                "plan": phase.get("log", []) if phase else [],
                "response": result,
                "mode": _active_mode,
            }
            app.layout.focus(input_buffer)
            app.invalidate()
            # Mostrar imágenes DESPUÉS del redraw del TUI para que no sean sobreescritas
            if _pending_display_images:
                paths = list(_pending_display_images)
                _pending_display_images.clear()
                loop.call_later(0.2, lambda: [_display_iterm2_image(p) for p in paths])

        def on_done(future):
            try:
                raw = future.result()
                # Preservar marcadores [AIA_IMG:...] antes de stripear Rich markup
                _img_markers = re.findall(r"\[AIA_IMG:[^\]]+\]", raw)
                result = _strip_rich_markup(raw)
                if _img_markers:
                    result = "\n".join(_img_markers) + ("\n" + result if result.strip() else "")
            except Exception as e:
                result = str(e)
            call_soon_threadsafe(lambda: update_ui(result), loop=loop)

        loop = asyncio.get_running_loop()
        future = run_in_executor_with_context(lambda: process(text, phase))
        future.add_done_callback(on_done)
        spinner_task = get_app().create_background_task(spinner_loop())
        return True

    input_buffer.accept_handler = lambda b: on_accept(b)

    kb = KeyBindings()

    @kb.add("enter")
    def _on_enter(event):
        if event.app.layout.current_buffer == input_buffer:
            input_buffer.validate_and_handle()

    @kb.add("tab")
    def _on_tab(event):
        """Tab desde output: volver a input para escribir."""
        if event.app.layout.current_buffer == output_buffer:
            event.app.layout.focus(input_buffer)

    @kb.add("s-tab")
    def _on_shift_tab(event):
        """Shift+Tab desde input: ir a output para scroll."""
        if event.app.layout.current_buffer == input_buffer:
            event.app.layout.focus(output_buffer)

    def _scroll_buf_up(buf: "Buffer", step: int = 3) -> None:
        """Mueve el cursor del buffer hacia arriba: prompt_toolkit auto-scrollea la ventana."""
        for _ in range(step):
            pos = buf.document.get_cursor_up_position()
            if pos:
                buf.cursor_position += pos

    def _scroll_buf_down(buf: "Buffer", step: int = 3) -> None:
        """Mueve el cursor del buffer hacia abajo: prompt_toolkit auto-scrollea la ventana."""
        for _ in range(step):
            pos = buf.document.get_cursor_down_position()
            if pos:
                buf.cursor_position += pos

    @kb.add(Keys.ScrollUp)
    def _on_scroll_up(event):
        """Scroll rueda arriba: scrollea el output via cursor-move."""
        _scroll_buf_up(output_buffer)
        event.app.invalidate()

    @kb.add(Keys.ScrollDown)
    def _on_scroll_down(event):
        """Scroll rueda abajo: scrollea el output via cursor-move."""
        _scroll_buf_down(output_buffer)
        event.app.invalidate()

    @kb.add("pageup")
    def _on_pageup(event):
        """Page Up: scrollea el output (usado via SSH cuando scroll wheel manda pageup)."""
        _scroll_buf_up(output_buffer, step=8)
        event.app.invalidate()

    @kb.add("pagedown")
    def _on_pagedown(event):
        """Page Down: scrollea el output (usado via SSH cuando scroll wheel manda pagedown)."""
        _scroll_buf_down(output_buffer, step=8)
        event.app.invalidate()

    @kb.add(Keys.Vt100MouseEvent, eager=True)
    def _on_mouse_event(event):
        """
        Intercepta eventos de mouse SGR/X10.
        - btn=64: scroll up  → mueve cursor output hacia arriba
        - btn=65: scroll down → mueve cursor output hacia abajo
        - resto: consume el evento sin acción (evita comportamiento erróneo en SSH)

        Usar cursor-move en output_buffer es más confiable que vertical_scroll directo:
        prompt_toolkit auto-scrollea cualquier Window para mostrar su cursor, incluso
        si no está enfocado.
        """
        data = event.data
        col = row = None
        sgr = re.match(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])", data)
        if sgr:
            btn = int(sgr.group(1))
            col = int(sgr.group(2))
            row = int(sgr.group(3))
            pressed = sgr.group(4) == "M"
        else:
            x10 = re.match(r"\x1b\[M(.)", data)
            btn = (ord(x10.group(1)) - 32) if x10 else None
            pressed = True

        if btn == 64:
            _scroll_buf_up(output_buffer)
            event.app.invalidate()
        elif btn == 65:
            _scroll_buf_down(output_buffer)
            event.app.invalidate()
        elif btn == 0 and pressed:
            # Click izquierdo: detectar si cae en la feedback bar, o hacer foco en output
            voted = False
            if _pending_feedback and col is not None and row is not None:
                try:
                    total_rows = event.app.output.get_size().rows
                    total_cols = event.app.output.get_size().columns
                except Exception:
                    total_rows = 24
                    total_cols = 80
                # feedback_bar row = total_rows - 1 (toolbar último, feedback penúltimo)
                if row == total_rows - 1:
                    vote = "up" if col <= total_cols // 2 else "down"
                    _register_vote(vote)
                    event.app.invalidate()
                    voted = True
            if not voted and event.app.layout.current_buffer == input_buffer:
                # Comportamiento Shift+Tab: ir a output para scroll
                event.app.layout.focus(output_buffer)
        # Resto de eventos: consumidos sin acción (evita dispatch posicional en SSH).

    @kb.add("escape")
    def _on_escape(event):
        global _active_mode
        if event.app.layout.current_buffer == output_buffer:
            event.app.layout.focus(input_buffer)
            return
        if live_monitor.is_active():
            live_monitor.stop()
            append_output("Monitor en vivo detenido.\n\n")
            event.app.invalidate()
            return
        if _active_mode:
            _active_mode = None
            _conversation_history.clear()
            append_output("[dim]Modo desactivado.[/]\n\n")
            event.app.invalidate()

    def _register_vote(vote: str) -> None:
        """Registra un voto (up/down), guarda en MongoDB y actualiza la UI."""
        global _pending_feedback, _feedback_voted
        if not _pending_feedback:
            return
        fb = _pending_feedback
        _pending_feedback = None
        _feedback_voted = vote
        import threading
        threading.Thread(
            target=save_feedback,
            kwargs={
                "question": fb["question"],
                "plan": fb["plan"],
                "response": fb["response"],
                "vote": 1 if vote == "up" else -1,
                "mode": fb.get("mode"),
            },
            daemon=True,
        ).start()

    def _feedback_bar_text():
        if _feedback_voted == "up":
            return [("fg:#27ae60 bold", "  👍")]
        if _feedback_voted == "down":
            return [("fg:#e74c3c bold", "  👎")]
        if _pending_feedback:
            return [
                ("fg:#27ae60 bold", "  👍"),
                ("", "        "),
                ("fg:#e74c3c bold", "👎"),
            ]
        return [("", "")]

    header = _create_header_window()
    feedback_bar = Window(
        content=FormattedTextControl(_feedback_bar_text),
        height=1,
        dont_extend_height=True,
    )
    input_window = Window(
        content=BufferControl(
            buffer=input_buffer,
            input_processors=[BeforeInput("› ", style="class:prompt")],
        ),
        height=Dimension(min=1),
        dont_extend_height=True,
    )
    def _toolbar_text():
        try:
            focused = get_app().layout.current_buffer
            if focused == output_buffer:
                return "↑↓ PgUp PgDn scroll | Tab o Escape para escribir"
        except Exception:
            pass
        t = (input_buffer.text or "").strip()
        scroll_hint = " | Shift+Tab para scroll"
        if t.startswith("!"):
            cmd = t[1:].strip()
            if cmd:
                return f"! {cmd}  →  shell{scroll_hint}"
            return f"! <comando>  ejecutar shell directo (ej: ! ls -la){scroll_hint}"
        if t.startswith("/"):
            completions = _get_slash_completions(t)
            if not completions:
                completions = ["/mcp list", "/mod list", "/cache delete", "/flush all", "/flush ollama", "/flush cache", "/flush history"] + [f"/mod {m}" for m in _get_available_modes()]
            try:
                width = get_app().output.get_size().columns
            except Exception:
                width = 80
            sep = " | "
            line1: list[str] = []
            line2: list[str] = []
            used = 0
            for i, c in enumerate(completions):
                chunk = (sep if i > 0 else "") + c
                if not line1 or used + len(chunk) <= width - len(scroll_hint):
                    line1.append(c)
                    used += len(chunk)
                else:
                    line2.append(c)
            text1 = sep.join(line1)
            if line2:
                return text1 + "\n" + sep.join(line2) + scroll_hint
            return text1 + scroll_hint
        if live_monitor.is_active():
            return [("bold fg:#e74c3c", "● EN VIVO"), ("#888888", " | /watch para detener | Escape para detener")]
        if _active_mode:
            mod = _get_mod_config()
            color = mod.get("color", "#ff8700") if mod else "#ff8700"
            mode_name = _active_mode.replace("modo_", "")
            branch = _get_git_branch(str(_project_root())) if mod and mod.get("contextFile") else None
            branch_str = f" ⎇ {branch}" if branch else ""
            mode_label = f"Modo {mode_name}{branch_str} activo"
            rest = f" | /help | exit o Escape para salir{scroll_hint}"
            extra_cmds = mod.get("slashCommands", []) if mod else []
            extra_hint = (" | " + " | ".join(extra_cmds)) if extra_cmds else ""
            return [("bold fg:" + color, mode_label), ("#888888", rest + extra_hint)]
        return [("bold fg:#ff8700", "? for shortcuts"), ("#888888", " | Shift+Tab o click para scroll | Tab para escribir")]
    toolbar = Window(
        content=FormattedTextControl(_toolbar_text),
        height=Dimension(min=1),
        dont_extend_height=True,
        style="class:bottom-toolbar",
    )

    root = HSplit([
        header,
        output_text_area,
        input_window,
        feedback_bar,
        toolbar,
    ])

    def _scrollbar_style() -> Style:
        """Scrollbar del mismo color que el banner según modo (desde mods.json)."""
        mod = _get_mod_config()
        c = mod.get("color", "#ff8700") if mod else "#ff8700"
        return Style.from_dict({
            "bottom-toolbar": "#888888",
            "scrollbar.background": f"bg:{c}",
            "scrollbar.button": f"bg:{c}",
            "scrollbar.arrow": f"fg:{c} bold",
        })

    layout = Layout(root, focused_element=input_buffer)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        style=DynamicStyle(_scrollbar_style),
        erase_when_done=True,
        mouse_support=False,  # Deshabilitado: gestionamos mouse manualmente
        enable_page_navigation_bindings=True,
    )

    # mouse_support=True hace que prompt_toolkit parsee eventos de mouse (Keys.Vt100MouseEvent)
    # tanto en terminal local como via SSH. Nuestro handler con eager=True consume todos los
    # eventos antes que load_mouse_bindings() (dispatch posicional), evitando comportamiento
    # erróneo en SSH. ?1006h (SGR) se habilita via pre_run para coordenadas > 223.
    def _enable_mouse() -> None:
        out = app.output
        out.write_raw("\x1b[?1000h")  # botones: click + scroll wheel
        out.write_raw("\x1b[?1006h")  # SGR: coordenadas correctas > 223
        out.flush()

    try:
        app.run(pre_run=_enable_mouse)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        try:
            out = app.output
            out.write_raw("\x1b[?1000l")
            out.write_raw("\x1b[?1006l")
            out.flush()
        except Exception:
            pass
    print("\nHasta luego.")
