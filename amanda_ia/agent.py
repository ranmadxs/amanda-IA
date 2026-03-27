"""Agente base - arquetipo para extender."""

import asyncio
import json
import re
import os
import subprocess
import time
import unicodedata
from pathlib import Path
import tomllib

from importlib.resources import files
from ollama import chat as ollama_chat, generate as ollama_generate
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
from amanda_ia.config import get_mcp_display_names, get_mcp_servers, get_mcp_servers_raw, set_mcp_server_enabled
from amanda_ia.config import get_mods_raw, get_mods, set_mod_enabled
from amanda_ia.config import _project_root
from amanda_ia.mcp_client import get_mcp_server_info, invalidate_mcp_cache, get_server_name_for_tool, get_server_transport, get_mode_help
from amanda_ia.classifier import classify_prompt, CLASSIFIER_MODEL
from amanda_ia.classifier_cache import get as cache_get, set_ as cache_set, delete_all as cache_delete_all
from amanda_ia.plan_cache import get as plan_cache_get, set_ as plan_cache_set, delete_all as plan_cache_delete_all
from amanda_ia import live_monitor
from amanda_ia.feedback import save_feedback

console = Console()


OLLAMA_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")

# Caché de rama git: (ruta, tiempo_última_consulta, branch)
_git_branch_cache: tuple[str, float, str] | None = None
_GIT_BRANCH_TTL = 5.0  # segundos entre consultas a git


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
    "filesystem": "Para list_directory: el directorio actual es {cwd}. Cuando pida \"carpeta actual\", pasa path=\"{cwd}\".",
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

    parts = [SYSTEM_PROMPT_BASE]
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
        mode_names = _get_servers_by_mode(servers, _active_mode)
        mcp_info = ", ".join(mode_names) if mode_names else None
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
        r = ollama_chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": f"Traduce SOLO al inglés, sin explicaciones. Responde únicamente con la traducción:\n{text.strip()}",
                }
            ],
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
            active = [s for s in servers if s.get("modo") == _active_mode]
            ctx_label = f"Modo {_active_mode.replace('modo_', '').replace('_', ' ').title()}"
        else:
            active = [s for s in servers if not s.get("modo")]
            ctx_label = "Modo general"
        active = [s for s in active if s.get("enabled") is not False]
        if not active:
            return f"[dim]No hay MCPs activos para {ctx_label}[/]"
        lines = []
        for s in active:
            name = s.get("name", "?")
            typ = "HTTP" if s.get("url") else "stdio"
            url_or_cmd = s.get("url") or f"{s.get('command', '')} {' '.join(str(a) for a in s.get('args', []))}"
            kw = s.get("keywords", [])
            kw_str = ", ".join(kw[:5]) + ("..." if len(kw) > 5 else "") if kw else "-"
            lines.append(f"  🟢 {name}\n    tipo: {typ}\n    {url_or_cmd}\n    keywords: {kw_str}")
        return f"MCP activos ({ctx_label}):\n\n" + "\n\n".join(lines)

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
        m = s.get("modo")
        if m and isinstance(m, str) and m.startswith("modo_"):
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


def _get_servers_by_mode(servers: list, mode: str) -> list[str]:
    """MCPs que tienen modo igual al indicado (ej: modo_warhammer)."""
    return [s["name"] for s in servers if s.get("modo") == mode and s.get("name")]


def _get_servers_for_general_mode(servers: list) -> list:
    """MCPs sin modo: solo estos se usan en modo general (clasificación por keywords)."""
    return [s for s in servers if not s.get("modo")]


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

        r = ollama_chat(
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


def _plan_execution(message: str, mcp_tools: list, phase: dict) -> None:
    """LLM genera el plan de ejecución como texto puro. Sin tools schemas → sin MCP calls."""
    tool_names = ", ".join(
        t.get("function", {}).get("name")
        for t in mcp_tools if t.get("function", {}).get("name")
    )
    system = (
        "Eres un planificador. Dado un prompt y una lista de tools disponibles, "
        "describe en UNA SOLA LÍNEA los pasos intermedios de ejecución.\n"
        "Formato: solo los pasos separados por ->. Pasos posibles: LLM, MCP(nombre_operacion).\n"
        "NO incluyas PROMPT ni RESPUESTA, solo los pasos del medio.\n"
        "Ejemplos:\n"
        "- 'hola' → LLM\n"
        "- 'lista archivos' → MCP(list_directory) -> LLM\n"
        "- 'modifica changelog con tags' → MCP(run_command) -> LLM -> MCP(run_command) -> LLM -> MCP(write_file)\n"
        "Responde ÚNICAMENTE la línea, sin texto adicional."
    )
    user = f"Tools disponibles: {tool_names}\nPrompt: {message}"
    try:
        cached_plan = plan_cache_get(message)
        if cached_plan is not None:
            phase.setdefault("log", []).append(f"PLAN>> {cached_plan}")  # noqa: B905
            return
        phase["value"] = "Planificando"  # noqa: B905
        phase.setdefault("log", []).append(f"LLM>>Ollama.{OLLAMA_MODEL} (plan)")  # noqa: B905
        response = ollama_chat(model=OLLAMA_MODEL, messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
        plan = (getattr(response.message, "content", None) or "").strip().split("\n")[0].strip()
        for noise in ("PROMPT ->", "PROMPT->", "-> RESPUESTA", "->RESPUESTA", "CLASIFICAR ->", "CLASIFICAR->"):
            plan = plan.replace(noise, "").strip().strip("->").strip()
        if plan:
            plan_cache_set(message, plan)
            phase.setdefault("log", []).append(f"PLAN>> {plan}")  # noqa: B905
    except Exception:
        pass


def process(message: str, phase: dict[str, str] | None = None) -> str:
    """Envía el mensaje a Ollama con tools y devuelve la respuesta."""
    global _active_mode, _conversation_history, _pending_live_action
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

    if msg_lower == "/help":
        if not _active_mode:
            return "[dim]Sin modo activo. Usa /mod <nombre> para activar uno.[/]"
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
                    ollama_generate(model=name, prompt="", keep_alive=0)
                    unloaded.append(name)
            if not unloaded:
                ollama_generate(model=OLLAMA_MODEL, prompt="", keep_alive=0)
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
        if _active_mode:
            # Modo activo: solo MCPs con ese modo
            selected = _get_servers_by_mode(servers, _active_mode)
        else:
            # Modo general: solo MCPs sin modo (los con modo nunca se usan aquí)
            servers_for_classification = _get_servers_for_general_mode(servers)
            cached = cache_get(message)
            if cached is not None:
                if phase is not None:
                    phase["value"] = "Cacheando"  # noqa: B905
                selected = cached
            else:
                if phase is not None:
                    phase["value"] = "Clasificando"  # noqa: B905
                    phase.setdefault("log", []).append(f"LLM>>Ollama.{CLASSIFIER_MODEL}")  # noqa: B905
                selected = classify_prompt(message, servers_for_classification)
                cache_set(message, selected)
            # Fallback: si clasificador devolvió [] pero el mensaje coincide con keywords, usar esos MCP
            if not selected:
                selected = _keyword_fallback(message, servers_for_classification)
            # Sin modo ni keywords: siempre incluido en modo general
            for s in servers_for_classification:
                if not s.get("keywords") and s.get("name") and s["name"] not in (selected or []):
                    selected = list(selected or []) + [s["name"]]
    else:
        pass  # Sin servidores: mantener selected ([] si bypass hora, None si sin config)

    # selected=None: builtin + todos los MCP. selected=[]: solo builtin.
    # selected=[...]: builtin + esos MCP. Siempre pasamos tools para que get_time funcione.
    tools = get_tools(selected)

    # Detectar si MCP no se cargaron (conexión fallida)
    mcp_tools = [t for t in tools if isinstance(t, dict) and t.get("type") == "function"]
    mcp_load_failed = selected and len(selected) > 0 and len(mcp_tools) == 0

    # Etapa de planificación: el LLM genera el flujo esperado (solo log, no afecta ejecución)
    if phase is not None:
        _plan_execution(message, mcp_tools, phase)

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

        # Paso 02: LLM con tools
        if phase is not None:
            phase["value"] = "Generando Respuesta"  # noqa: B905
            phase.setdefault("log", []).append(f"LLM>>Ollama.{OLLAMA_MODEL}")  # noqa: B905
        response = ollama_chat(model=OLLAMA_MODEL, messages=messages, tools=tools)
        msg = response.message

        # Paso 03-04: ejecutar MCPs si el LLM devolvió tool_calls
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            messages.append(_msg_to_dict(msg))
            for tc in msg.tool_calls:
                name = tc.function.name
                if name == "list_mcp_databases":
                    name = "list_databases"
                server_name = get_server_name_for_tool(name)
                if phase is not None:
                    phase["value"] = f"mcp_exe@{server_name}" if server_name else "mcp_exe"  # noqa: B905
                args = _normalize_arguments(getattr(tc.function, "arguments", None))
                if name in ("list_databases", "list-databases") and args:
                    args = {}
                if args.get("path") in (".", "./", ""):
                    args["path"] = cwd
                if selected and len(selected) > 0 and get_server_name_for_tool(name) == "wahapedia" and args:
                    args = _translate_wahapedia_args(args)
                if phase is not None:
                    phase.setdefault("log", []).append(_fmt_tool_call(server_name, name, args))  # noqa: B905
                result = execute_tool(name, args)
                last_tool_result = result
                messages.append({"role": "tool", "tool_name": name, "content": result})
                if name == "start_live_monitor":
                    _pending_live_action = "start"
                elif name == "stop_live_monitor":
                    _pending_live_action = "stop"

        else:
            # Fallback: modelo devolvió JSON como texto en vez de tool_calls
            content = (getattr(msg, "content", None) or "").strip()
            tool_parsed = _try_parse_tool_json(content)
            if tool_parsed:
                name, params = tool_parsed
                if name == "list_mcp_databases":
                    name = "list_databases"
                server_name = get_server_name_for_tool(name)
                if phase is not None:
                    phase["value"] = f"mcp_exe@{server_name}" if server_name else "mcp_exe"  # noqa: B905
                if name in ("list_databases", "list-databases") and params:
                    params = {}
                if selected and len(selected) > 0 and server_name == "wahapedia" and params:
                    params = _translate_wahapedia_args(params)
                if phase is not None:
                    phase.setdefault("log", []).append(_fmt_tool_call(server_name, name, params))  # noqa: B905
                result = execute_tool(name, params)
                last_tool_result = result
                if name == "start_live_monitor":
                    _pending_live_action = "start"
                elif name == "stop_live_monitor":
                    _pending_live_action = "stop"
                messages.append({"role": "assistant", "content": content})
                lang_hint = " (spanglish para WH40K)" if selected and "wahapedia" in selected else ""
                messages.append({"role": "user", "content": f"Resultado de {name}: {result}\n\nResponde la pregunta del usuario con esta información. Responde en español{lang_hint}."})
            elif content:
                # Respuesta directa sin tools
                if mcp_load_failed:
                    content += "\n\n[dim]Nota: No se cargaron las herramientas MCP. ¿Están los servidores corriendo? (ej: cd aia-mcp && poetry run mcp all --http). Prueba /cache delete si el clasificador falló.[/]"
                _conversation_history = messages[1:] + [{"role": "assistant", "content": content}]
                return content
            else:
                return "[dim]Sin respuesta.[/]"

        # Paso 05: LLM sin tools para interpretar los resultados de los MCPs
        if phase is not None:
            phase["value"] = "Generando Respuesta"  # noqa: B905
            phase.setdefault("log", []).append(f"LLM>>Ollama.{OLLAMA_MODEL}")  # noqa: B905
        final = ollama_chat(model=OLLAMA_MODEL, messages=messages)
        content = (getattr(final.message, "content", None) or "").strip()
        if content:
            _conversation_history = messages[1:] + [{"role": "assistant", "content": content}]
            return content
        if last_tool_result:
            _conversation_history = messages[1:] + [{"role": "assistant", "content": last_tool_result}]
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

    def append_output(text: str) -> None:
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

        def on_done(future):
            try:
                result = _strip_rich_markup(future.result())
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
        elif btn == 0 and pressed and _pending_feedback and col is not None and row is not None:
            # Click izquierdo: detectar si cae en la feedback bar
            # La feedback bar está 2 filas antes del borde inferior (toolbar=1, feedback=2)
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

    # Con mouse_support=False, prompt_toolkit NO agrega load_mouse_bindings()
    # (dispatch posicional que falla en SSH). Habilitamos solo ?1000h (botones +
    # scroll) y ?1006h (SGR encoding) manualmente via pre_run para que nuestro
    # handler de Keys.Vt100MouseEvent sea el único que procese eventos de mouse.
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
