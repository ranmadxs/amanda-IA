"""Agente base - arquetipo para extender."""

import os
from pathlib import Path

import tomllib

from importlib.resources import files
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.rule import Rule

console = Console()


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
    texts = [
        f"  [bold]aia[/] v{_get_version()}",
        "  [dim]Modelo ejemplo · Sin LLM[/]",
        f"  [dim]{cwd}[/]",
    ]
    for i in range(5):
        icon = f"[bold orange1]{icon_lines[i]}[/]" if i < len(icon_lines) else ""
        txt = texts[i] if i < len(texts) else ""
        console.print(icon + txt)


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


def process(message: str) -> str:
    """Procesa un mensaje del usuario. Extender aquí."""
    return "NO TENGO MEMORIA Y_:Y"
