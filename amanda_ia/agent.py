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
from amanda_ia.config import get_mcp_display_names, get_mcp_servers
from amanda_ia.mcp_client import get_mcp_server_info
from amanda_ia.classifier import classify_prompt

console = Console()


OLLAMA_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT_TEMPLATE = """Eres un asistente útil. Tienes acceso a herramientas (tools) configuradas en .aia/settings.json y .aia/mcp.json.
Usa las tools cuando el usuario lo necesite.

IMPORTANTE para list_directory y operaciones de archivos: el directorio actual es {cwd}
Cuando el usuario pida "carpeta actual", "este directorio" o similar, pasa path="{cwd}" a list_directory.

Responde en español de forma natural."""


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


def process(message: str, phase: dict[str, str] | None = None) -> str:
    """Envía el mensaje a Ollama con tools y devuelve la respuesta."""
    servers = get_mcp_servers()
    server_names = [s["name"] for s in servers if s.get("name")]

    if servers:
        if phase is not None:
            phase["value"] = "Clasificando"  # noqa: B905
        selected = classify_prompt(message, servers)
    else:
        selected = None  # Sin MCP: usar builtin

    if phase is not None:
        phase["value"] = "Pensando"  # noqa: B905
    # Sin MCP: builtin. Con MCP y clasificador devolvió []: no tools (saludo, etc.)
    if selected is None:
        tools = get_tools(None)
    elif selected:
        tools = get_tools(selected)
    else:
        tools = []
    cwd = os.getcwd()
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(cwd=cwd)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]

    try:
        while True:
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
                    args = _normalize_arguments(getattr(tc.function, "arguments", None))
                    result = execute_tool(name, args)
                    messages.append({"role": "tool", "tool_name": name, "content": result})
                continue

            content = (getattr(msg, "content", None) or "").strip()
            if content:
                return content
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
            append_output("exit - salir | quit - salir\n")
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
