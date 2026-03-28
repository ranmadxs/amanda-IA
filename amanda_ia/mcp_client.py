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


def _stdio_params(server: dict[str, Any]) -> StdioServerParameters:
    """Crea StdioServerParameters expandiendo $HOME/~ en command y args."""
    def _expand(s: str) -> str:
        return os.path.expanduser(os.path.expandvars(s))

    # Construir env con PATH enriquecido para que npx y otros binarios de Homebrew sean encontrados
    env = dict(os.environ)
    for extra in ("/opt/homebrew/bin", "/usr/local/bin"):
        if extra not in env.get("PATH", ""):
            env["PATH"] = extra + ":" + env.get("PATH", "")
    # Expandir variables del server (ej: GITHUB_PERSONAL_ACCESS_TOKEN)
    if server.get("env"):
        for k, v in server["env"].items():
            env[k] = _expand(str(v))

    return StdioServerParameters(
        command=_expand(server["command"]),
        args=[_expand(a) for a in server.get("args", [])],
        env=env,
        cwd=server.get("cwd"),
    )


async def _call_tool_http(url: str, name: str, arguments: dict[str, Any]) -> str:
    """Llama a una tool en servidor MCP HTTP."""
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            return _extract_tool_result(result)


async def _call_tool_stdio(server: dict[str, Any], name: str, arguments: dict[str, Any]) -> str:
    """Llama a una tool en servidor MCP stdio (proceso)."""
    params = _stdio_params(server)
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
    params = _stdio_params(server)
    async with stdio_client(params, errlog=_STDIO_ERRLOG) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools_result = await session.list_tools()
            names = [t.name for t in tools_result.tools]
            schemas = [_mcp_tool_to_ollama(t) for t in tools_result.tools]
            return names, schemas


# Cache: evita reconectar a cada servidor en cada mensaje.
# Se invalida al cambiar de modo (/mod) o con /cache delete.
_tool_map_cache: dict[str, dict[str, Any]] | None = None
_schemas_cache: list[dict[str, Any]] | None = None


def _fetch_server_tools(
    server_names: list[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """
    Conecta solo a servidores no cacheados. Acumula el cache globalmente.
    Así una llamada con server_names=["airbnb"] enriquece el cache con sus tools,
    y llamadas posteriores sin server_names las encuentran sin reconectar.
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
            log.warning("MCP server %s: %s", name, msg)
    _tool_map_cache = result_map
    _schemas_cache = result_schemas
    return result_map, result_schemas


def _get_tool_to_server_map(server_names: list[str] | None = None) -> dict[str, dict[str, Any]]:
    """Mapa tool_name -> server config. Usa cache global acumulativo."""
    if _tool_map_cache is not None and not server_names:
        return _tool_map_cache
    return _fetch_server_tools(server_names)[0]


# Tools que no aceptan parámetros; el modelo a veces inventa cluster, etc.
_TOOLS_NO_ARGS = frozenset({"list_databases", "list-databases"})
_EMPTY_PARAMS = {"type": "object", "properties": {}, "additionalProperties": False}


def _sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Para list_databases: forzar parameters vacío para que el modelo no invente cluster, etc."""
    fn = schema.get("function", {})
    if fn.get("name") in _TOOLS_NO_ARGS:
        schema = dict(schema)
        schema["function"] = dict(fn)
        schema["function"]["parameters"] = _EMPTY_PARAMS
    return schema


def get_mcp_tool_schemas(server_names: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Schemas de tools MCP en formato Ollama.
    Solo conecta a los servidores en server_names (no carga mongodb si no se necesita).
    """
    if server_names is not None and len(server_names) == 0:
        return []
    tool_map, schemas = _fetch_server_tools(server_names)
    schemas = [_sanitize_schema(s) for s in schemas]
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


def get_server_name_for_tool(tool_name: str) -> str | None:
    """Nombre del servidor MCP que tiene esta tool (ej: 'wahapedia', 'mongodb')."""
    tool_map = _get_tool_to_server_map()
    server = tool_map.get(tool_name)
    return server.get("name") if server else None


def get_server_transport(server_name: str) -> str:
    """Retorna el protocolo del servidor: 'http', 'npx' o 'sh'."""
    tool_map = _get_tool_to_server_map()
    for server in tool_map.values():
        if server.get("name") == server_name:
            if server.get("url"):
                return "http"
            cmd = os.path.basename(server.get("command", ""))
            return "npx" if cmd == "npx" else "sh"
    return "sh"


def invalidate_mcp_cache() -> None:
    """Invalida el cache de tools MCP. Llamado al cambiar de modo o con /cache delete."""
    global _tool_map_cache, _schemas_cache
    _tool_map_cache = None
    _schemas_cache = None


def list_tools_for_server(server: dict[str, Any]) -> list[dict[str, Any]]:
    """Lista tools de un servidor específico sin usar cache. Retorna schemas Ollama."""
    try:
        if server.get("url"):
            _, schemas = anyio.run(_list_tools_http, server["url"])
        elif server.get("command"):
            _, schemas = anyio.run(_list_tools_stdio, server)
        else:
            return []
        return schemas
    except BaseException as e:
        log.warning("list_tools_for_server %s: %s", server.get("name"), _format_mcp_error(e))
        return []


def call_tool_on_server(server: dict[str, Any], tool_name: str, arguments: dict[str, Any]) -> str:
    """Llama a una tool en un servidor específico sin usar cache."""
    try:
        if server.get("url"):
            return anyio.run(_call_tool_http, server["url"], tool_name, arguments)
        elif server.get("command"):
            return anyio.run(_call_tool_stdio, server, tool_name, arguments)
        return "Error: servidor sin comando ni URL"
    except BaseException as e:
        return f"Error MCP: {_format_mcp_error(e)}"


async def _list_tools_described(server: dict[str, Any]) -> list[tuple[str, str]]:
    """Retorna [(tool_name, description), ...] conectando directamente al servidor."""
    if server.get("url"):
        async with streamable_http_client(server["url"]) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [(t.name, getattr(t, "description", "") or "") for t in result.tools]
    elif server.get("command"):
        params = _stdio_params(server)
        async with stdio_client(params, errlog=_STDIO_ERRLOG) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [(t.name, getattr(t, "description", "") or "") for t in result.tools]
    return []


def get_mode_help(mode_key: str) -> str:
    """
    Retorna ayuda conversacional del modo activo: ejemplos de preguntas
    y comandos slash disponibles.
    """
    from amanda_ia.config import get_mods_raw

    mods_raw = get_mods_raw()
    mod = next((m for m in mods_raw if m.get("key") == mode_key), None)
    mode_label = mode_key.replace("modo_", "").replace("_", " ").title()

    lines = [f"Modo [bold]{mode_label}[/bold] — ¿Qué podés preguntarme?\n\n"]

    # Ejemplos de preguntas por sección
    examples = mod.get("examples", []) if mod else []
    if examples:
        for section in examples:
            title = section.get("title", "")
            items = section.get("items", [])
            if title:
                lines.append(f"[bold]{title}[/bold]\n")
            for item in items:
                lines.append(f'  "{item}"\n')
            lines.append("\n")
    else:
        lines.append("  (Sin ejemplos configurados para este modo)\n\n")

    # Comandos slash del modo
    slash_cmds = mod.get("slashCommands", []) if mod else []
    cmd_defs = mod.get("commands", {}) if mod else {}
    if slash_cmds:
        lines.append("[bold]Comandos:[/bold]\n")
        cmd_desc = {
            "/watch":    "stream de lecturas en tiempo real",
            "/test":     "corre los tests del proyecto",
            "/diff":     "muestra los cambios actuales",
            "/git-log":  "historial de commits",
            "/files":    "archivos modificados",
        }
        for cmd in slash_cmds:
            desc = cmd_desc.get(cmd, "")
            if not desc and isinstance(cmd_defs.get(cmd), dict):
                desc = cmd_defs[cmd].get("shell", "")[:50]
            lines.append(f"  [dim]{cmd}[/dim]  {desc}\n")

    return "".join(lines).rstrip() + "\n"
