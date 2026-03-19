"""Configuración siguiendo el estándar de Claude.

Rutas:
  Scope    │ Ruta
  ─────────┼──────────────────────────────────────────────────────
  user     │ ~/.aia/settings.json
  local    │ ./.aia/settings.local.json (relativo al proyecto)
  project  │ ./.aia/mcp.json (lista dinámica de servidores MCP)

Precedencia: user < project < local (local sobreescribe).

Tools builtin: .aia/settings.json -> tools[] (como mcp.json servers).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def _home() -> Path:
    return Path.home()


def _project_root() -> Path:
    """Raíz del proyecto (donde está .aia)."""
    cwd = Path.cwd()
    # 1) cwd
    if (cwd / ".aia").is_dir():
        return cwd
    # 2) subdirs (workspace con amanda-IA/, etc.)
    for child in sorted(cwd.iterdir()):
        if child.is_dir() and (child / ".aia").is_dir():
            return child
    # 3) padres
    for p in cwd.parents:
        if (p / ".aia").is_dir():
            return p
    return cwd


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _merge(base: dict, override: dict) -> dict:
    """Fusiona override sobre base (override gana)."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get_settings() -> dict[str, Any]:
    """Carga settings fusionando user, project y local."""
    home = _home()
    project = _project_root()

    user_path = home / ".aia" / "settings.json"
    project_path = project / ".aia" / "settings.json"
    local_path = project / ".aia" / "settings.local.json"

    settings = {}
    settings = _merge(settings, _load_json(user_path))
    settings = _merge(settings, _load_json(project_path))
    settings = _merge(settings, _load_json(local_path))

    return settings


def get_mcp_config() -> dict[str, Any]:
    """Carga .mcp.json del proyecto (formato Claude, legacy)."""
    project = _project_root()
    mcp_path = project / ".mcp.json"
    return _load_json(mcp_path)


def get_tools_config() -> list[dict[str, Any]]:
    """
    Tools builtin habilitadas desde .aia/settings.json.
    Formato: {"tools": [{"name": "get_temperature", "enabled": true}, ...]}
    Disponibles: get_time.
    Similar a mcp.json servers.
    """
    project = _project_root()
    settings_path = project / ".aia" / "settings.json"
    data = _load_json(settings_path)
    tools = data.get("tools", [])
    if not isinstance(tools, list):
        return []
    return [t for t in tools if isinstance(t, dict) and t.get("enabled") is not False]


def get_mcp_servers_raw() -> list[dict[str, Any]]:
    """Todos los servidores de .aia/mcp.json (incluyendo deshabilitados)."""
    project = _project_root()
    mcp_path = project / ".aia" / "mcp.json"
    data = _load_json(mcp_path)
    servers = data.get("servers", [])
    return [s for s in servers if isinstance(s, dict)]


def set_mcp_server_enabled(name: str, enabled: bool) -> bool:
    """Actualiza enabled de un servidor en .aia/mcp.json. Retorna True si OK."""
    project = _project_root()
    mcp_path = project / ".aia" / "mcp.json"
    data = _load_json(mcp_path)
    servers = data.get("servers", [])
    if not isinstance(servers, list):
        return False
    for s in servers:
        if s.get("name") == name:
            s["enabled"] = enabled
            mcp_path.parent.mkdir(parents=True, exist_ok=True)
            with open(mcp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
    return False


def get_mcp_servers() -> list[dict[str, Any]]:
    """
    Lista dinámica de servidores MCP desde .aia/mcp.json.
    Formato:
    - HTTP: {"name": "temperatura", "url": "http://..."}
    - Stdio: {"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"]}
    Sustituye ${workspaceFolder} por la raíz del proyecto.
    """
    project = _project_root()
    mcp_path = project / ".aia" / "mcp.json"
    data = _load_json(mcp_path)
    servers = data.get("servers", [])
    if not isinstance(servers, list):
        return []
    result = []
    workspace = str(project)
    cwd = str(Path.cwd())
    for s in servers:
        if not isinstance(s, dict):
            continue
        if s.get("enabled") is False:
            continue
        s = dict(s)
        if s.get("type") == "builtin":
            result.append(s)
        elif s.get("url"):
            result.append(s)
        elif s.get("command"):
            args = s.get("args", [])
            s["args"] = [
                a.replace("${workspaceFolder}", workspace).replace("${cwd}", cwd)
                if isinstance(a, str) else a
                for a in args
            ]
            # Expandir ${VAR} en env desde os.environ
            if "env" in s and isinstance(s["env"], dict):
                s["env"] = {
                    k: v if not (isinstance(v, str) and v.startswith("${") and v.endswith("}"))
                    else os.environ.get(v[2:-1], v)
                    for k, v in s["env"].items()
                }
            result.append(s)
    return result


def get_mcp_url() -> str | None:
    """
    Obtiene la URL del primer servidor MCP con precedencia:
    1. Variable de entorno MCP_URL
    2. .aia/mcp.json -> servers[0].url
    3. settings.json -> mcpUrl
    4. settings.json -> mcpServers -> primer servidor HTTP
    5. .mcp.json (legacy) -> mcpServers -> primer servidor HTTP
    """
    url = os.environ.get("MCP_URL")
    if url:
        return url

    servers = get_mcp_servers()
    if servers:
        return servers[0].get("url")

    settings = get_settings()
    url = settings.get("mcpUrl")
    if url:
        return url

    srv = settings.get("mcpServers", {})
    for name, cfg in srv.items():
        if isinstance(cfg, dict):
            if cfg.get("type") == "http" and "url" in cfg:
                return cfg["url"]
            if "url" in cfg:
                return cfg["url"]

    mcp = get_mcp_config()
    srv = mcp.get("mcpServers", {})
    for name, cfg in srv.items():
        if isinstance(cfg, dict) and "url" in cfg:
            return cfg["url"]

    return None


def get_mcp_display_names() -> str | None:
    """
    Nombres de los servidores MCP registrados en .aia/mcp.json.
    Para mostrar en GUI, ej: "temperatura" o "temperatura, otro".
    """
    servers = get_mcp_servers()
    names = [s.get("name", "mcp") for s in servers if s.get("name")]
    return ", ".join(names) if names else None


def get_config_paths() -> dict[str, str]:
    """Rutas de los archivos de config (para mostrar en UI)."""
    home = _home()
    project = _project_root()
    return {
        "user": str(home / ".aia" / "settings.json"),
        "local": str(project / ".aia" / "settings.local.json"),
        "project_mcp": str(project / ".aia" / "mcp.json"),
        "project_tools": str(project / ".aia" / "settings.json"),
    }
