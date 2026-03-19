"""Registro y ejecución de tools."""

import logging

from amanda_ia.tools import builtin
from amanda_ia.config import get_tools_config

from amanda_ia.mcp_client import call_mcp_tool, get_mcp_tools, get_mcp_tool_schemas

log = logging.getLogger(__name__)

# Registry: nombre -> función. Tools disponibles para configurar en .aia/settings.json
BUILTIN_REGISTRY = {
    "get_temperature": builtin.get_temperature,
    "get_time": builtin.get_time,
    "get_unit_stats": builtin.get_unit_stats,
    "search_wahapedia": builtin.search_wahapedia,
}

# Cache de tools MCP (se llena al primer uso)
_mcp_tool_names: list[str] | None = None


def _mcp_has_tool(name: str) -> bool:
    """True si la tool está en MCP."""
    global _mcp_tool_names
    if _mcp_tool_names is None:
        _mcp_tool_names = get_mcp_tools()
    return name in _mcp_tool_names


def _get_builtin_tools() -> list:
    """Tools builtin habilitadas en .aia/settings.json."""
    config = get_tools_config()
    return [BUILTIN_REGISTRY[t["name"]] for t in config if t.get("name") in BUILTIN_REGISTRY]


def get_tools(server_names: list[str] | None = None):
    """
    Lista de tools para Ollama: builtin desde .aia/settings.json + schemas MCP.
    Si server_names está definido, solo incluye tools de esos servidores MCP.
    """
    tools: list = _get_builtin_tools()
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
