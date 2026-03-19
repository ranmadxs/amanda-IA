"""Tests de configuración (README: .aia/mcp.json, .aia/settings.json)."""

import json

import pytest

from amanda_ia import config


class TestProjectRoot:
    """_project_root busca .aia en cwd o padres."""

    def test_finds_aia_in_cwd(self, tmp_path, monkeypatch):
        (tmp_path / ".aia").mkdir()
        monkeypatch.chdir(tmp_path)
        assert config._project_root() == tmp_path

    def test_finds_aia_in_parent(self, tmp_path, monkeypatch):
        (tmp_path / ".aia").mkdir()
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        assert config._project_root() == tmp_path


class TestGetToolsConfig:
    """Tools desde .aia/settings.json - enabled=true incluidas."""

    def test_loads_tools_from_settings(self, tmp_aia, tmp_settings_json, monkeypatch):
        monkeypatch.setattr(config, "_project_root", lambda: tmp_aia.parent)
        result = config.get_tools_config()
        assert len(result) == 1
        assert result[0]["name"] == "get_time"
        assert result[0]["enabled"] is True

    def test_excludes_disabled_tools(self, tmp_aia, monkeypatch):
        monkeypatch.setattr(config, "_project_root", lambda: tmp_aia.parent)
        (tmp_aia / "settings.json").write_text(
            json.dumps({"tools": [{"name": "get_time", "enabled": False}]}),
            encoding="utf-8",
        )
        result = config.get_tools_config()
        assert len(result) == 0

    def test_empty_when_no_settings(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "_project_root", lambda: tmp_path)
        result = config.get_tools_config()
        assert result == []


class TestGetMcpServers:
    """Servidores desde .aia/mcp.json - HTTP, stdio, sustitución de variables."""

    def test_loads_http_servers(self, tmp_aia, monkeypatch):
        monkeypatch.setattr(config, "_project_root", lambda: tmp_aia.parent)
        (tmp_aia / "mcp.json").write_text(
            json.dumps({
                "servers": [{"name": "temperatura", "url": "http://localhost:8001/mcp"}],
            }),
            encoding="utf-8",
        )
        result = config.get_mcp_servers()
        assert len(result) == 1
        assert result[0]["name"] == "temperatura"
        assert result[0]["url"] == "http://localhost:8001/mcp"

    def test_substitutes_workspace_folder(self, tmp_aia, monkeypatch):
        monkeypatch.setattr(config, "_project_root", lambda: tmp_aia.parent)
        (tmp_aia / "mcp.json").write_text(
            json.dumps({
                "servers": [{
                    "name": "fs",
                    "command": "npx",
                    "args": ["-y", "@mcp/server-fs", "${workspaceFolder}"],
                }],
            }),
            encoding="utf-8",
        )
        result = config.get_mcp_servers()
        assert len(result) == 1
        assert str(tmp_aia.parent) in result[0]["args"]

    def test_excludes_disabled_servers(self, tmp_aia, monkeypatch):
        monkeypatch.setattr(config, "_project_root", lambda: tmp_aia.parent)
        (tmp_aia / "mcp.json").write_text(
            json.dumps({
                "servers": [
                    {"name": "a", "url": "http://a"},
                    {"name": "b", "url": "http://b", "enabled": False},
                ],
            }),
            encoding="utf-8",
        )
        result = config.get_mcp_servers()
        assert len(result) == 1
        assert result[0]["name"] == "a"
