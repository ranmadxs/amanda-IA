"""CLI de Amanda-IA."""

import argparse
import logging
import os

from dotenv import load_dotenv

load_dotenv()

# Reducir ruido de MCP en stderr (evita "MCP server mongodb: ..." en cada prompt)
# Con AIA_DEBUG=1 se muestran warnings de conexión MCP
_mcp_log = logging.getLogger("amanda_ia.mcp_client")
_mcp_log.setLevel(logging.WARNING if os.environ.get("AIA_DEBUG") else logging.ERROR)

from amanda_ia.agent import run, process
from amanda_ia.agent import console


def main():
    """Punto de entrada."""
    parser = argparse.ArgumentParser(prog="aia")
    parser.add_argument("-m", "--message", help="Mensaje único: responde y termina sin abrir la CLI")
    parser.add_argument("--modo", help="Modo activo: warhammer, monitor, etc. Con -m ejecuta el mensaje en ese modo.")
    args = parser.parse_args()

    if args.message is not None:
        if args.modo and args.modo.strip():
            import amanda_ia.agent as agent_mod
            mode_key = f"modo_{args.modo.strip()}" if not args.modo.strip().startswith("modo_") else args.modo.strip()
            agent_mod._active_mode = mode_key
        response = process(args.message)
        console.print(response)
        return

    if args.modo and args.modo.strip():
        import amanda_ia.agent as agent_mod
        mode_key = f"modo_{args.modo.strip()}" if not args.modo.strip().startswith("modo_") else args.modo.strip()
        agent_mod._active_mode = mode_key
    run()
