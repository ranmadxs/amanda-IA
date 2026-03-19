"""Cliente MCP: HTTP (streamable-http) y stdio (proceso)."""

from __future__ import annotations

import logging
import os
from typing import Any

import anyio

log = logging.getLogger(__name__)


def _format_mcp_error(exc: BaseException) -> str:
    """Extrae mensaje útil de ExceptionGroup (ej: ConnectError, Connection refused)."""
    if hasattr(exc, "exceptions"):
        for sub in getattr(exc, "exceptions", ()):
            name = type(sub).__name__
            if name not in ("GeneratorExit", "CancelledError"):
                return str(sub)
    return str(exc)
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from amanda_ia.config import get_mcp_servers

# stderr del proceso stdio se redirige a devnull para no romper la UI
_STDIO_ERRLOG = open(os.devnull, "w")


async def _call_tool_http(url: str, name: str, arguments: dict[str, Any]) -> str:
    """Llama a una tool en servidor MCP HTTP."""
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return _extract_tool_result(result)


async def _call_tool_stdio(server: dict[str, Any], name: str, arguments: dict[str, Any]) -> str:
    """Llama a una tool en servidor MCP stdio (proceso)."""
    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env=server.get("env"),
        cwd=server.get("cwd"),
    )
    async with stdio_client(params, errlog=_STDIO_ERRLOG) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return _extract_tool_result(result)


def _extract_tool_result(result) -> str:
    """Extrae el texto del resultado de call_tool."""
    if getattr(result, "isError", False):
        return f"Error MCP: {result.content}"
    if result.content:
        for part in result.content:
            if hasattr(part, "text"):
                return part.text
        return str(result.content[0])
    return ""


async def _list_tools_http(url: str) -> tuple[list[str], list[dict]]:
    """Lista tools de servidor MCP HTTP. Retorna (nombres, schemas Ollama)."""
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            names = [t.name for t in tools_result.tools]
            schemas = [_mcp_tool_to_ollama(t) for t in tools_result.tools]
            return names, schemas


def _mcp_tool_to_ollama(tool) -> dict[str, Any]:
    """Convierte tool MCP a formato Ollama (type, function, name, description, parameters)."""
    schema = getattr(tool, "inputSchema", None) or {}
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": getattr(tool, "description", "") or "",
            "parameters": schema if isinstance(schema, dict) else {"type": "object", "properties": {}},
        },
    }


async def _list_tools_stdio(server: dict[str, Any]) -> tuple[list[str], list[dict]]:
    """Lista tools de servidor MCP stdio. Retorna (nombres, schemas Ollama)."""
    params = StdioServerParameters(
        command=server["command"],
        args=server.get("args", []),
        env=server.get("env"),
        cwd=server.get("cwd"),
    )
    async with stdio_client(params, errlog=_STDIO_ERRLOG) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            names = [t.name for t in tools_result.tools]
            schemas = [_mcp_tool_to_ollama(t) for t in tools_result.tools]
            return names, schemas


# Cache: evita reconectar a cada servidor en cada mensaje
_tool_map_cache: dict[str, dict[str, Any]] | None = None
_schemas_cache: list[dict[str, Any]] | None = None


def _fetch_server_tools(
    server_names: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """
    Conecta solo a los servidores indicados. Si server_names es None, conecta a todos.
    Solo carga los MCP que realmente se necesitan.
    """
    global _tool_map_cache, _schemas_cache
    servers = get_mcp_servers()
    if server_names is not None:
        servers = [s for s in servers if s.get("name") in server_names]
    result_map: dict[str, dict[str, Any]] = dict(_tool_map_cache or {})
    result_schemas: list[dict[str, Any]] = list(_schemas_cache or [])
    loaded = {s.get("name") for s in result_map.values() if s.get("name")}
    for server in servers:
        name = server.get("name")
        if name in loaded:
            continue
        try:
            if server.get("url"):
                names, schemas = anyio.run(_list_tools_http, server["url"])
            elif server.get("command"):
                names, schemas = anyio.run(_list_tools_stdio, server)
            else:
                continue
            for t in names:
                result_map[t] = server
            result_schemas.extend(schemas)
            loaded.add(name)
        except BaseException as e:
            msg = _format_mcp_error(e)
            log.warning("MCP server %s: %s", server.get("name", "?"), msg)
    _tool_map_cache = result_map
    _schemas_cache = result_schemas
    return result_map, result_schemas


def _get_tool_to_server_map(server_names: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Mapa tool_name -> server config. Si server_names, solo carga esos."""
    if _tool_map_cache is not None and (server_names is None or not server_names):
        return _tool_map_cache
    return _fetch_server_tools(server_names)[0]


def get_mcp_tool_schemas(server_names: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Schemas de tools MCP en formato Ollama.
    Solo conecta a los servidores en server_names (no carga mongodb si no se necesita).
    """
    if server_names is not None and len(server_names) == 0:
        return []
    tool_map, schemas = _fetch_server_tools(server_names)
    if not server_names:
        return schemas
    return [
        s for s in schemas
        if tool_map.get(s.get("function", {}).get("name", ""), {}).get("name") in server_names
    ]


def call_mcp_tool(name: str, arguments: dict[str, Any]) -> str | None:
    """
    Ejecuta una tool vía MCP. Enruta al servidor que tiene la tool (HTTP o stdio).
    Retorna el resultado o None si MCP no está configurado/falla.
    """
    tool_map = _get_tool_to_server_map()
    server = tool_map.get(name)
    if not server:
        return None
    try:
        if server.get("url"):
            return anyio.run(_call_tool_http, server["url"], name, arguments)
        return anyio.run(_call_tool_stdio, server, name, arguments)
    except BaseException as e:
        msg = _format_mcp_error(e)
        hint = ""
        if "connect" in msg.lower() or "refused" in msg.lower() or "attempts failed" in msg.lower():
            hint = " ¿Está el servidor MCP corriendo? (ej: poetry run mcp wahapedia --http)"
        return f"Error MCP: {msg}{hint}"


def get_mcp_server_info() -> str | None:
    """
    Nombres de los servidores MCP configurados.
    Retorna None si no hay MCP configurado.
    """
    servers = get_mcp_servers()
    if not servers:
        return None
    return ", ".join(s.get("name", "mcp") for s in servers)


def get_mcp_tools() -> list[str]:
    """Lista de tools disponibles en todos los servidores MCP (HTTP + stdio)."""
    return list(_get_tool_to_server_map().keys())


def invalidate_mcp_cache() -> None:
    """Invalida la caché de tools MCP. Útil si cambias .aia/mcp.json en caliente."""
    global _tool_map_cache, _schemas_cache
    _tool_map_cache = None
    _schemas_cache = None
