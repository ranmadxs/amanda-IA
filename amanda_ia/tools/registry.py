"""Registro y ejecución de tools."""

from amanda_ia.tools import builtin

from amanda_ia.mcp_client import call_mcp_tool, get_mcp_tools

# Mapa nombre -> función builtin (fallback)
_BUILTIN_TOOLS = {
    "get_temperature": builtin.get_temperature,
    "get_time": builtin.get_time,
}

# Cache de tools MCP (se llena al primer uso)
_mcp_tool_names: list[str] | None = None


def _mcp_has_tool(name: str) -> bool:
    """True si la tool está en MCP."""
    global _mcp_tool_names
    if _mcp_tool_names is None:
        _mcp_tool_names = get_mcp_tools()
    return name in _mcp_tool_names


def get_tools():
    """Lista de funciones para pasar a Ollama."""
    return [builtin.get_temperature, builtin.get_time]


def execute_tool(name: str, arguments: dict) -> str:
    """Ejecuta una tool por nombre. Usa MCP si está configurado, sino builtin."""
    if _mcp_has_tool(name):
        result = call_mcp_tool(name, arguments)
        if result is not None:
            return result
    fn = _BUILTIN_TOOLS.get(name)
    if not fn:
        return f"Error: tool '{name}' no encontrada"
    try:
        result = fn(**arguments)
        return str(result)
    except TypeError as e:
        return f"Error en argumentos: {e}"
    except Exception as e:
        return f"Error: {e}"
