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
    parser.add_argument("--web", action="store_true", help="Levanta el chatbot como servidor web (por defecto puerto 8080)")
    parser.add_argument("--port", type=int, default=8080, help="Puerto para --web (default: 8080)")
    parser.add_argument("--agent-api", action="store_true", help="Levanta solo el agent API HTTP en puerto 8081 (sin UI web)")
    parser.add_argument("--api-port", type=int, default=8081, help="Puerto para --agent-api (default: 8081)")
    args = parser.parse_args()

    if args.agent_api:
        mode_key = None
        if args.modo and args.modo.strip():
            mode_key = f"modo_{args.modo.strip()}" if not args.modo.strip().startswith("modo_") else args.modo.strip()
        from amanda_ia.agent_api import run_agent_api
        from amanda_ia.aia_avatar import run_aia_avatar
        import signal
        run_agent_api(port=args.api_port)
        _, avatar_port = run_aia_avatar()
        if mode_key:
            import amanda_ia.agent as agent_mod
            agent_mod._active_mode = mode_key
        from amanda_ia.config import get_ports
        ports = get_ports()
        print(f"  puerto {args.api_port}  → agent_api   http://127.0.0.1:{args.api_port}")
        print(f"  puerto {avatar_port}   → aia_avatar  http://localhost:{avatar_port}")
        print("Ctrl+C para detener")
        signal.pause()
        return

    if args.web:
        mode_key = None
        if args.modo and args.modo.strip():
            mode_key = f"modo_{args.modo.strip()}" if not args.modo.strip().startswith("modo_") else args.modo.strip()
        from amanda_ia.agent_api import run_agent_api
        from amanda_ia.aia_avatar import run_aia_avatar
        run_agent_api()
        _, avatar_port = run_aia_avatar()
        if mode_key:
            import amanda_ia.agent as agent_mod
            agent_mod._active_mode = mode_key
        from amanda_ia.web_server import run_web
        run_web(port=args.port, avatar_port=avatar_port)
        return

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
