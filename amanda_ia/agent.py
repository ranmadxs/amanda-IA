"""Agente base - arquetipo para extender."""

import os
from pathlib import Path

import tomllib

from importlib.resources import files
from ollama import chat as ollama_chat
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.rule import Rule

from amanda_ia.tools import get_tools, execute_tool
from amanda_ia.mcp_client import get_mcp_server_info

console = Console()

OLLAMA_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")

SYSTEM_PROMPT = """Eres un asistente útil. Tienes acceso a herramientas (tools) que puedes usar cuando el usuario lo necesite:
- get_temperature: para consultar la temperatura de una ciudad
- get_time: para saber la hora actual

Usa las tools cuando el usuario pregunte por temperatura, hora, clima, etc. Responde en español de forma natural."""


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


def _print_header():
    """Imprime el header estilo Claude Code."""
    cwd = os.getcwd()
    icon_lines = _load_banner()
    mcp_info = get_mcp_server_info()
    tools_label = f"Ollama + {mcp_info}" if mcp_info else "Ollama + Tools"
    texts = [
        f"  [bold]aia[/] v{_get_version()}",
        f"  [dim]{OLLAMA_MODEL} · {tools_label}[/]",
        f"  [dim]{cwd}[/]",
    ]
    for i in range(5):
        icon = f"[bold orange1]{icon_lines[i]}[/]" if i < len(icon_lines) else ""
        txt = texts[i] if i < len(texts) else ""
        console.print(icon + txt)


def _msg_to_dict(msg) -> dict:
    """Convierte Message a dict para añadir a messages."""
    d = {"role": getattr(msg, "role", "assistant"), "content": getattr(msg, "content", "") or ""}
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        d["tool_calls"] = [
            {
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": getattr(tc.function, "arguments", {}) or {},
                },
            }
            for tc in msg.tool_calls
        ]
    return d


def process(message: str) -> str:
    """Envía el mensaje a Ollama con tools y devuelve la respuesta."""
    tools = get_tools()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
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
                    args = getattr(tc.function, "arguments", None) or {}
                    result = execute_tool(name, args)
                    messages.append({"role": "tool", "tool_name": name, "content": result})
                continue

            content = (getattr(msg, "content", None) or "").strip()
            if content:
                return content
            return "[dim]Sin respuesta.[/]"

    except Exception as e:
        return f"[dim red]Error: {e}\n¿Ollama está corriendo? (ollama serve)[/]"


def run():
    """Loop principal del agente."""
    _print_header()
    while True:
        try:
            console.print(Rule(style="dim"))
            user_input = pt_prompt(
                "› ",
                bottom_toolbar="? for shortcuts",
                style=Style.from_dict({"bottom-toolbar": "#888888"}),
            ).strip()
            console.print(Rule(style="dim"))
        except (EOFError, KeyboardInterrupt):
            console.print("\nHasta luego.")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            console.print("Hasta luego.")
            break
        if user_input == "?":
            console.print("[dim]exit - salir | quit - salir[/]")
            continue
        response = process(user_input)
        console.print(response)
