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
from prompt_toolkit.eventloop.utils import call_soon_threadsafe, run_in_executor_with_context
from prompt_toolkit.layout import HSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.document import Document
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.processors import BeforeInput
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.styles import Style

from rich.console import Console

from amanda_ia.tools import get_tools, execute_tool
from amanda_ia.config import get_mcp_display_names, get_mcp_servers, get_mcp_servers_raw, set_mcp_server_enabled
from amanda_ia.mcp_client import get_mcp_server_info, invalidate_mcp_cache
from amanda_ia.classifier import classify_prompt
from amanda_ia.classifier_cache import get as cache_get, set_ as cache_set, delete_all as cache_delete_all

console = Console()


OLLAMA_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT_BASE = """Eres un asistente útil. Tienes acceso a herramientas (tools) configuradas en .aia/settings.json y .aia/mcp.json.
Usa las tools cuando el usuario lo necesite.

IMPORTANTE: Cuando el usuario pida datos (listar, consultar, litros, porcentaje, nivel de agua), USA LA TOOL INMEDIATAMENTE. No preguntes "¿Quieres que...?" ni pidas confirmación. Ejecuta la tool y responde con el resultado. NUNCA respondas "no puedo" si tienes una tool que puede ayudar.

Responde en español de forma natural."""

# Fallback cuando mcp.json no tiene "systemPrompt" (opcional por servidor)
SERVER_PROMPT_HINTS = {
    "get_time": "Si el usuario pregunta la hora, fecha o \"qué hora es\", USA get_time (sin parámetros).",
    "filesystem": "Para list_directory: el directorio actual es {cwd}. Cuando pida \"carpeta actual\", pasa path=\"{cwd}\".",
    "mongodb": "MongoDB: conexión preconfigurada. NO pases host, port, username ni password. list-databases sin parámetros. list-collections requiere solo database. NUNCA inventes datos.",
    "tinaja": "Acumulador/estanque: Para litros, porcentaje o nivel de agua, EJECUTA get_lectura_actual() YA. Si falla, usa calculate_tinaja_level(50). Responde con el resultado. NUNCA digas 'no puedo'.",
}


def _build_system_prompt(selected: list[str] | None, tools: list, cwd: str) -> str:
    """
    Construye el system prompt dinámicamente según los MCP/servidores cargados.
    Solo incluye instrucciones para los servidores que están en uso.
    """
    if not tools:
        return """Eres un asistente útil y amigable. No tienes herramientas en este momento.
Responde en español de forma natural y cordial. Para saludos (hola, buenos días) responde breve y amablemente."""

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


def _get_header_formatted_text():
    """Header como formatted text para prompt_toolkit (banner + textos + rule)."""
    cwd = os.getcwd()
    icon_lines = _load_banner()
    mcp_info = get_mcp_display_names() or get_mcp_server_info()
    tools_label = f"Ollama + {mcp_info}" if mcp_info else "Ollama + Tools"
    texts = [
        f"  aia v{_get_version()}",
        f"  {OLLAMA_MODEL} · {tools_label}",
        f"  {cwd}",
    ]
    lines = []
    for i in range(5):
        icon = icon_lines[i] if i < len(icon_lines) else ""
        txt = texts[i] if i < len(texts) else ""
        if icon:
            lines.append(("bold fg:#ff8700", icon))
        if txt:
            lines.append(("fg:ansigray", " " + txt if icon else txt))
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
            kw = s.get("keywords", [])
            kw_str = ", ".join(kw[:5]) + ("..." if len(kw) > 5 else "") if kw else "-"
            lines.append(f"  {name}\n    tipo: {typ} | {status}\n    {url_or_cmd}\n    keywords: {kw_str}")
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
    msg_stripped = message.strip()
    msg_lower = msg_stripped.lower()

    # Comandos slash
    if msg_lower == "/cache delete":
        cache_delete_all()
        invalidate_mcp_cache()
        return "[dim]Cache borrada (clasificador + MCP tools).[/]"

    if msg_lower.startswith("/mcp "):
        return _run_mcp_command(msg_stripped.split())

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
        cached = cache_get(message)
        if cached is not None:
            if phase is not None:
                phase["value"] = "Cacheando"  # noqa: B905
            selected = cached
        else:
            if phase is not None:
                phase["value"] = "Clasificando"  # noqa: B905
            selected = classify_prompt(message, servers)
            cache_set(message, selected)
        # Fallback: si clasificador devolvió [] pero el mensaje coincide con keywords, usar esos MCP
        if not selected:
            selected = _keyword_fallback(message, servers)
        # Bypass: consultas de temperatura → forzar carga de temperatura MCP
        _temp_keywords = ("temperatura", "clima", "grados", "qué temperatura", "cómo está el clima")
        if any(k in msg_lower for k in _temp_keywords) and any(s.get("name") == "temperatura" for s in servers):
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
                if phase is not None:
                    phase["value"] = "Ejecutando"  # noqa: B905
                messages.append(_msg_to_dict(msg))
                for tc in msg.tool_calls:
                    name = tc.function.name
                    args = _normalize_arguments(getattr(tc.function, "arguments", None))
                    result = execute_tool(name, args)
                    last_tool_result = result
                    messages.append({"role": "tool", "tool_name": name, "content": result})
                continue

            content = (getattr(msg, "content", None) or "").strip()
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
                if "Pensando" in line or "Clasificando" in line:
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


def _scroll_output_to_bottom(output_buffer: Buffer) -> None:
    """Coloca el cursor al final para que la vista haga auto-scroll al último contenido."""
    output_buffer.cursor_position = len(output_buffer.text)


def run():
    """Loop principal del agente."""
    input_buffer = Buffer(name="input", multiline=False)
    output_buffer = Buffer(name="output")

    def append_output(text: str) -> None:
        output_buffer.insert_text(text)
        _scroll_output_to_bottom(output_buffer)

    def on_accept(buff: Buffer) -> bool:
        text = buff.text.strip()
        buff.reset()
        app = get_app()

        if not text:
            return True
        if text.lower() in ("exit", "quit"):
            app.exit(result=None)
            return True
        if text == "?":
            append_output("exit | quit - salir | /cache delete - borrar cache | /mcp list - listar MCP | /mcp <name> disabled|enabled\n")
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
                        _scroll_output_to_bottom(output_buffer)
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
            append_output(result + "\n\n")
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

    header = _create_header_window()
    output_window = Window(
        content=BufferControl(
            buffer=output_buffer,
            focusable=False,
            lexer=_QuestionHighlightLexer(),
        ),
        wrap_lines=True,
        always_hide_cursor=True,
    )
    input_window = Window(
        content=BufferControl(
            buffer=input_buffer,
            input_processors=[BeforeInput("› ", style="class:prompt")],
        ),
        height=Dimension(min=1),
        dont_extend_height=True,
    )
    toolbar = Window(
        content=FormattedTextControl("? for shortcuts"),
        height=Dimension(min=1),
        dont_extend_height=True,
        style="class:bottom-toolbar",
    )

    root = HSplit([
        header,
        output_window,
        input_window,
        toolbar,
    ])

    layout = Layout(root, focused_element=input_buffer)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=True,
        style=Style.from_dict({"bottom-toolbar": "#888888"}),
        erase_when_done=True,
    )

    try:
        app.run()
    except (EOFError, KeyboardInterrupt):
        pass
    print("\nHasta luego.")
