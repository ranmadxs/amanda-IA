"""Cliente MCP por HTTP para conectar con aia-mcp."""

import os
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def _get_mcp_url() -> str | None:
    """URL del servidor MCP desde env. Ej: http://localhost:8000/mcp"""
    return os.environ.get("MCP_URL")


async def _call_tool_async(url: str, name: str, arguments: dict[str, Any]) -> str:
    """Llama a una tool en el servidor MCP."""
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            if getattr(result, "isError", False):
                return f"Error MCP: {result.content}"
            if result.content:
                for part in result.content:
                    if hasattr(part, "text"):
                        return part.text
                return str(result.content[0])
            return ""


def call_mcp_tool(name: str, arguments: dict[str, Any]) -> str | None:
    """
    Ejecuta una tool vía MCP HTTP. Retorna el resultado o None si MCP no está configurado/falla.
    """
    url = _get_mcp_url()
    if not url:
        return None
    try:
        return anyio.run(_call_tool_async, url, name, arguments)
    except Exception as e:
        return f"Error MCP: {e}"


def get_mcp_server_info() -> str | None:
    """
    Conecta al servidor MCP y devuelve info del servidor (ej: "aia-mcp 0.1.0").
    Retorna None si MCP no está configurado o falla la conexión.
    """
    url = _get_mcp_url()
    if not url:
        return None

    async def _get_info():
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                result = await session.initialize()
                si = result.serverInfo
                return f"{si.name} {si.version}".strip()

    try:
        return anyio.run(_get_info)
    except Exception:
        return None


def get_mcp_tools() -> list[str]:
    """Lista de tools disponibles en MCP (para enrutar execute_tool)."""
    url = _get_mcp_url()
    if not url:
        return []

    async def _list():
        async with streamable_http_client(url) as (read_stream, write_stream, _):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                return [t.name for t in tools_result.tools]

    try:
        return anyio.run(_list)
    except Exception:
        return []
