"""Agente base - arquetipo para extender."""

import asyncio
import json
import re
import os
from pathlib import Path
import tomllib

from importlib.resources import files
from ollama import chat as ollama_chat
from prompt_toolkit import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.eventloop.utils import call_soon_threadsafe, run_in_executor_with_context
from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEvent, MouseEventType


class _ScrollableBufferControl(BufferControl):
    """
    BufferControl que maneja SCROLL_UP/DOWN moviendo el cursor para poder
    escrollear más allá del límite vertical_scroll=0 (bug en Window._scroll_up).
    """

    def mouse_handler(self, mouse_event: MouseEvent):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            b = self.buffer
            row = b.document.cursor_position_row
            if row > 0:
                step = min(5, row)
                new_row = max(0, row - step)
                b.cursor_position = b.document.translate_row_col_to_index(new_row, 0)
                get_app().invalidate()
            return None
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            b = self.buffer
            row = b.document.cursor_position_row
            max_row = max(0, b.document.line_count - 1)
            if row < max_row:
                step = min(5, max_row - row)
                new_row = min(max_row, row + step)
                b.cursor_position = b.document.translate_row_col_to_index(new_row, 0)
                get_app().invalidate()
            return None
        return super().mouse_handler(mouse_event)
from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.page_navigation import (
    scroll_page_up,
    scroll_page_down,
    scroll_backward,
    scroll_forward,
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
from amanda_ia.config import _project_root
from amanda_ia.mcp_client import get_mcp_server_info, invalidate_mcp_cache, get_server_name_for_tool
from amanda_ia.classifier import classify_prompt
from amanda_ia.classifier_cache import get as cache_get, set_ as cache_set, delete_all as cache_delete_all

console = Console()


OLLAMA_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT_BASE = """Eres un asistente útil. Tienes acceso a herramientas (tools) configuradas en .aia/settings.json y .aia/mcp.json.
Usa las tools cuando el usuario lo necesite.

IMPORTANTE: Cuando el usuario pida datos (listar, consultar, litros, porcentaje, nivel de agua), USA LA TOOL INMEDIATAMENTE. No preguntes "¿Quieres que...?" ni pidas confirmación. Ejecuta la tool y responde con el resultado. NUNCA respondas "no puedo" si tienes una tool que puede ayudar.

La respuesta final debe estar SIEMPRE en español."""

# Fallback cuando mcp.json no tiene "systemPrompt" (opcional por servidor)
SERVER_PROMPT_HINTS = {
    "get_time": "Si el usuario pregunta la hora, fecha o \"qué hora es\", USA get_time (sin parámetros).",
    "filesystem": "Para list_directory: el directorio actual es {cwd}. Cuando pida \"carpeta actual\", pasa path=\"{cwd}\".",
    "mongodb": "MongoDB: conexión preconfigurada. NO pases host, port, username ni password. Para listar bases de datos: USA list_databases (no list_mcp_databases). NUNCA pases parámetros: ni cluster, ni cluster_name, ni format. Siempre arguments vacío {}. list-collections requiere solo database. NUNCA inventes datos.",
    "monitor": "Acumulador/estanque: Para litros, porcentaje o nivel: get_lectura_actual(). Para velocidad de disminución del agua: get_velocidad_disminucion_agua() (historial MongoDB). Si falla lectura, usa calculate_tinaja_level(50). Responde con el resultado. NUNCA digas 'no puedo'.",
    "wahapedia": "Wahapedia está en inglés. TRADUCE query y faction al inglés. Unidades: get_unit_stats/search_wahapedia. Estratagemas: get_stratagems(faction). Ej: 'estratagemas adeptus custodes' -> get_stratagems('adeptus-custodes').",
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
    # Idioma final: español; spanglish solo para Warhammer 40K
    if selected and "wahapedia" in selected:
        parts.append("\n\nIMPORTANTE: Para Warhammer 40K usa spanglish: responde en español pero nombres de unidades, estratagemas y términos técnicos pueden quedar en inglés.")
    else:
        parts.append("\n\nIMPORTANTE: Responde siempre en español. La respuesta final debe estar en español.")
    return "\n".join(parts)


def _get_version() -> str:
    """Versión desde pyproject.toml."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with open(pyproject, "rb") as f:
        data = tomllib.load(f)
    return data["tool"]["poetry"]["version"]


def _load_banner() -> list[str]:
    """Carga el icono desde resources/banner.txt."""
    path = files("amanda_ia") / "resources" / "banner.txt"
    return path.read_text().strip().split("\n")


def _load_banner_wh40k() -> list[str]:
    """Carga el banner WH40K desde resources/banner_wh40k.txt."""
    path = files("amanda_ia") / "resources" / "banner_wh40k.txt"
    return path.read_text().strip().split("\n")


def _load_banner_h2o() -> list[str]:
    """Carga el banner H2O desde resources/banner_h2o.txt."""
    path = files("amanda_ia") / "resources" / "banner_h2o.txt"
    return path.read_text().strip().split("\n")


def _get_header_formatted_text():
    """Header como formatted text para prompt_toolkit (banner + textos + rule)."""
    cwd = os.getcwd()
    icon_lines = _load_banner()
    wh40k_lines = _load_banner_wh40k()
    h2o_lines = _load_banner_h2o()
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
        f"  aia v{_get_version()}",
        f"  {OLLAMA_MODEL} · {tools_label}",
        f"  {cwd}",
    ]
    lines = []
    num_lines = 5
    for i in range(num_lines):
        if _active_mode == "modo_warhammer":
            combined_icon = wh40k_lines[i] if i < len(wh40k_lines) else ""
        elif _active_mode == "modo_monitor":
            combined_icon = h2o_lines[i] if i < len(h2o_lines) else ""
        else:
            combined_icon = icon_lines[i] if i < len(icon_lines) else ""
        txt = texts[i] if i < len(texts) else ""
        if combined_icon:
            if _active_mode == "modo_warhammer":
                banner_style = "bold fg:#9b59b6"
            elif _active_mode == "modo_monitor":
                banner_style = "bold fg:#3498db"
            else:
                banner_style = "bold fg:#ff8700"
            lines.append((banner_style, combined_icon))
        if txt:
            lines.append(("fg:ansigray", " " + txt if combined_icon else txt))
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
    if "name" not in content or "parameters" not in content:
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
        lines = []
        for s in servers:
            name = s.get("name", "?")
            typ = "HTTP" if s.get("url") else "stdio"
            url_or_cmd = s.get("url") or f"{s.get('command', '')} {' '.join(str(a) for a in s.get('args', []))}"
            enabled = s.get("enabled") is not False
            status = "enabled" if enabled else "disabled"
            modo = s.get("modo")
            kw = s.get("keywords", [])
            kw_str = ", ".join(kw[:5]) + ("..." if len(kw) > 5 else "") if kw else "-"
            modo_str = f" | modo: {modo}" if modo else ""
            lines.append(f"  {name}\n    tipo: {typ} | {status}{modo_str}\n    {url_or_cmd}\n    keywords: {kw_str}")
        return "MCP servidores:\n\n" + "\n\n".join(lines)

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


def _get_available_modes() -> list[str]:
    """Modos definidos en mcp.json (ej: warhammer, monitor)."""
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
    return ["/mcp", "/cache delete"] + [f"/modo {m}" for m in modes]


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


def process(message: str, phase: dict[str, str] | None = None) -> str:
    """Envía el mensaje a Ollama con tools y devuelve la respuesta."""
    global _active_mode
    msg_stripped = message.strip()
    msg_lower = msg_stripped.lower()

    # Comandos slash: /modo <nombre>
    if msg_lower.startswith("/modo "):
        mode_name = msg_lower[6:].strip()
        mode_key = f"modo_{mode_name}" if mode_name and not mode_name.startswith("modo_") else mode_name
        servers = get_mcp_servers()
        if any(s.get("modo") == mode_key for s in servers):
            _active_mode = mode_key
            label = mode_name.replace("_", " ").title()
            return f"[dim]Modo {label} activado. Escribe 'exit' para salir.[/]"
        return f"[dim]Modo '{mode_name}' no existe. Modos: {', '.join(_get_available_modes())}[/]"

    if msg_lower == "/cache delete":
        cache_delete_all()
        invalidate_mcp_cache()
        return "[dim]Cache borrada (clasificador + MCP tools).[/]"

    if msg_lower.startswith("/mcp"):
        parts = msg_stripped.split()
        if len(parts) == 1:
            parts = ["/mcp", "list"]
        return _run_mcp_command(parts)

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
                selected = classify_prompt(message, servers_for_classification)
                cache_set(message, selected)
            # Fallback: si clasificador devolvió [] pero el mensaje coincide con keywords, usar esos MCP
            if not selected:
                selected = _keyword_fallback(message, servers_for_classification)
            # Sin modo ni keywords: siempre incluido en modo general
            for s in servers_for_classification:
                if not s.get("keywords") and s.get("name") and s["name"] not in (selected or []):
                    selected = list(selected or []) + [s["name"]]
            # Bypass: consultas de temperatura → forzar carga de temperatura MCP
            _temp_keywords = ("temperatura", "clima", "grados", "qué temperatura", "cómo está el clima")
            if any(k in msg_lower for k in _temp_keywords) and any(
                s.get("name") == "temperatura" for s in servers_for_classification
            ):
                if "temperatura" not in (selected or []):
                    selected = list(selected or []) + ["temperatura"]
    else:
        pass  # Sin servidores: mantener selected ([] si bypass hora, None si sin config)

    # selected=None: builtin + todos los MCP. selected=[]: solo builtin.
    # selected=[...]: builtin + esos MCP. Siempre pasamos tools para que get_time funcione.
    tools = get_tools(selected)

    # Detectar si MCP no se cargaron (conexión fallida)
    mcp_tools = [t for t in tools if isinstance(t, dict) and t.get("type") == "function"]
    mcp_load_failed = selected and len(selected) > 0 and len(mcp_tools) == 0

    cwd = os.getcwd()
    system_prompt = _build_system_prompt(selected, tools, cwd)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    try:
        last_tool_result = None
        while True:
            if phase is not None:
                phase["value"] = "Generando Respuesta"  # noqa: B905
            response = ollama_chat(
                model=OLLAMA_MODEL,
                messages=messages,
                tools=tools,
            )
            msg = response.message

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
                    # list_databases no acepta parámetros; el modelo a veces inventa cluster, cluster_name, format
                    if name in ("list_databases", "list-databases") and args:
                        args = {}
                    # Wahapedia está en inglés: traducir query/faction si vienen en español
                    # Solo consultar MCP cuando hay servidores cargados (evita cargar mongodb etc. para get_time)
                    if selected and len(selected) > 0 and get_server_name_for_tool(name) == "wahapedia" and args:
                        args = _translate_wahapedia_args(args)
                    result = execute_tool(name, args)
                    last_tool_result = result
                    messages.append({"role": "tool", "tool_name": name, "content": result})
                continue

            content = (getattr(msg, "content", None) or "").strip()
            # Fallback: modelo devolvió JSON como texto en vez de tool_calls
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
                result = execute_tool(name, params)
                last_tool_result = result
                messages.append({"role": "assistant", "content": content})
                lang_hint = " (spanglish para WH40K)" if selected and "wahapedia" in selected else ""
                messages.append({"role": "user", "content": f"Resultado de {name}: {result}\n\nResponde la pregunta del usuario con esta información. Responde en español{lang_hint}."})
                continue

            if content:
                if mcp_load_failed:
                    content += "\n\n[dim]Nota: No se cargaron las herramientas MCP. ¿Están los servidores corriendo? (ej: cd aia-mcp && poetry run mcp all --http). Prueba /cache delete si el clasificador falló.[/]"
                return content
            # Fallback: si el modelo no formateó la respuesta, usar el resultado de la tool
            if last_tool_result:
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
                    padded = line + " " * max(0, width - len(line))
                    return [("bg:#2d2d2d fg:white", padded)]
                if "Pensando" in line or "Clasificando" in line or "mcp_exe" in line:
                    # Efecto luz: letra resaltada en gris claro, resto en gris oscuro
                    parts = []
                    highlight_next = False
                    for c in line:
                        if c == ZW:
                            highlight_next = True
                        elif highlight_next:
                            parts.append(("fg:#999999", c))
                            highlight_next = False
                        else:
                            parts.append(("fg:#555555", c))
                    return parts if parts else [("fg:#555555", line)]
                return [("", line)]
            except IndexError:
                return []

        return get_line


# Spinner: mismos caracteres braille que Ollama CLI (progress/spinner.go)
SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
ZW = "\u200b"  # Zero-width space para marcar la letra resaltada


def _scroll_output(output_buffer: Buffer, force_bottom: bool = False) -> None:
    """
    Si el contenido es corto, muestra desde arriba (sin espacio vacío).
    Si es largo, scroll al final para ver lo último.
    """
    lines = output_buffer.text.count("\n") + 1
    if force_bottom or lines > 25:
        output_buffer.cursor_position = len(output_buffer.text)
    else:
        output_buffer.cursor_position = 0


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
        focus_on_click=True,
    )
    output_text_area = Window(
        content=output_control,
        wrap_lines=True,
        right_margins=[ScrollbarMargin(display_arrows=True)],
    )

    def append_output(text: str, scroll_to_bottom: bool = False) -> None:
        output_buffer.insert_text(text)
        _scroll_output(output_buffer, force_bottom=scroll_to_bottom)

    def on_accept(buff: Buffer) -> bool:
        global _active_mode
        text = buff.text.strip()
        buff.reset()
        app = get_app()

        if not text:
            return True
        if text.lower() in ("exit", "quit"):
            if _active_mode:
                _active_mode = None
                append_output("[dim]Modo desactivado.[/]\n\n")
                app.invalidate()
                return True
            app.exit(result=None)
            return True
        # Guardar en historial (flecha arriba) para mensajes válidos
        if text and text != "?":
            input_history.append_string(text)
        if text == "?":
            append_output("exit | quit - salir | /modo warhammer - modo Warhammer 40K | /cache delete - borrar cache | /mcp list - listar MCP | /mcp <name> disabled|enabled\n")
            app.invalidate()
            return True

        phase = {"value": "Clasificando"}
        append_output("› " + text + "\n")
        append_output(SPINNER_FRAMES[0] + " Clasificando\n")
        app.invalidate()

        spinner_task = None

        def get_spinner_label():
            return phase.get("value", "Pensando")

        async def spinner_loop():
            nonlocal spinner_task
            i = 1
            try:
                while True:
                    lines = output_buffer.text.rsplit("\n", 2)
                    if len(lines) >= 2:
                        frame = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
                        label = get_spinner_label()
                        idx = i % len(label) if label else 0
                        animated = label[:idx] + ZW + label[idx:] if label else ""
                        output_buffer.text = lines[0] + "\n" + frame + " " + animated + "\n"
                        _scroll_output(output_buffer, force_bottom=True)
                        app.invalidate()
                    i += 1
                    await asyncio.sleep(0.1)  # 100ms como Ollama
            except asyncio.CancelledError:
                pass

        def update_ui(result: str):
            nonlocal spinner_task
            if spinner_task and not spinner_task.done():
                spinner_task.cancel()
            lines = output_buffer.text.rsplit("\n", 2)
            output_buffer.text = (lines[0] if lines else "") + "\n\n"
            append_output(result + "\n\n", scroll_to_bottom=len(result) > 500)
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

    @kb.add(Keys.ScrollUp)
    def _on_scroll_up(event):
        """Scroll del mouse: subir cuando output está enfocado. Usar scroll_backward para poder pasar entre preguntas."""
        if event.app.layout.current_buffer == output_buffer:
            scroll_backward(event, half=True)

    @kb.add(Keys.ScrollDown)
    def _on_scroll_down(event):
        """Scroll del mouse: bajar cuando output está enfocado."""
        if event.app.layout.current_buffer == output_buffer:
            scroll_forward(event, half=True)

    @kb.add("escape")
    def _on_escape(event):
        global _active_mode
        if event.app.layout.current_buffer == output_buffer:
            event.app.layout.focus(input_buffer)
            return
        if _active_mode:
            _active_mode = None
            append_output("[dim]Modo desactivado.[/]\n\n")
            event.app.invalidate()

    header = _create_header_window()
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
        if t.startswith("/"):
            # Filtrar por aproximación desde /
            completions = _get_slash_completions(t)
            base = " | ".join(completions) if completions else "/mcp | /cache delete | /modo warhammer | /modo monitor"
            return base + scroll_hint
        if _active_mode:
            mode_label = f"Modo {_active_mode.replace('modo_', '')} activo"
            rest = f" | exit o Escape para salir{scroll_hint}"
            if _active_mode == "modo_warhammer":
                return [("bold fg:#9b59b6", mode_label), ("#888888", rest)]
            if _active_mode == "modo_monitor":
                return [("bold fg:#3498db", mode_label), ("#888888", rest)]
            return mode_label + rest
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
        toolbar,
    ])

    def _scrollbar_style() -> Style:
        """Scrollbar del mismo color que el banner según modo."""
        if _active_mode == "modo_warhammer":
            c = "#9b59b6"
        elif _active_mode == "modo_monitor":
            c = "#3498db"
        else:
            c = "#ff8700"
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
        mouse_support=True,
        enable_page_navigation_bindings=True,
    )

    try:
        app.run()
    except (EOFError, KeyboardInterrupt):
        pass
    print("\nHasta luego.")
