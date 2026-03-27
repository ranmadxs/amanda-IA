"""Registro y ejecución de tools."""

import logging

from amanda_ia.tools import builtin
from amanda_ia.config import get_tools_config

from amanda_ia.mcp_client import call_mcp_tool, get_mcp_tools, get_mcp_tool_schemas

log = logging.getLogger(__name__)

# Registry: nombre -> función. Tools disponibles para configurar en .aia/settings.json
BUILTIN_REGISTRY = {
    "get_time": builtin.get_time,
}

def _mcp_has_tool(name: str) -> bool:
    """True si la tool está en MCP. Usa el tool_map_cache que se actualiza por modo."""
    if name in BUILTIN_REGISTRY:
        return False
    return name in get_mcp_tools()


def _get_builtin_tools() -> list:
    """Tools builtin habilitadas en .aia/settings.json."""
    config = get_tools_config()
    return [BUILTIN_REGISTRY[t["name"]] for t in config if t.get("name") in BUILTIN_REGISTRY]


def get_tools(server_names: list[str] | None = None):
    """
    Lista de tools para Ollama: builtin desde .aia/settings.json + schemas MCP.
    Si server_names está definido, solo incluye tools de esos servidores MCP.
    Si server_names == [] (clasificador devolvió vacío), no conecta a MCP.
    """
    tools: list = _get_builtin_tools()
    if server_names is not None and len(server_names) == 0:
        return tools  # Clasificador devolvió []: solo builtin (get_time, mcp_tool), sin MCP
    try:
        mcp_schemas = get_mcp_tool_schemas(server_names)
        tools.extend(mcp_schemas)
    except Exception as e:
        log.warning("No se pudieron cargar tools MCP: %s", e)
    return tools


def execute_tool(name: str, arguments: dict) -> str:
    """Ejecuta una tool por nombre. MCP primero, luego builtin (si configurada)."""
    if _mcp_has_tool(name):
        result = call_mcp_tool(name, arguments)
        if result is not None:
            return result
        return "Error: MCP no disponible para esta tool"
    fn = BUILTIN_REGISTRY.get(name)
    if not fn:
        return f"Error: tool '{name}' no encontrada"
    try:
        result = fn(**arguments)
        return str(result)
    except TypeError as e:
        return f"Error en argumentos: {e}"
    except Exception as e:
        return f"Error: {e}"
