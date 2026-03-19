"""Tests del registro de tools (execute_tool, get_tools)."""

import pytest

from amanda_ia.tools import registry


class TestExecuteTool:
    """execute_tool: builtin primero, salidas esperadas."""

    def test_get_time_returns_formatted_string(self):
        result = registry.execute_tool("get_time", {})
        assert ":" in result and "/" in result
        # Formato HH:MM:SS - DD/MM/YYYY
        parts = result.split(" - ")
        assert len(parts) == 2
        assert len(parts[0].split(":")) == 3
        assert len(parts[1].split("/")) == 3

    def test_unknown_tool_returns_error(self):
        result = registry.execute_tool("tool_inexistente", {})
        assert "Error" in result
        assert "no encontrada" in result


class TestGetTools:
    """get_tools: builtin desde settings + MCP schemas."""

    def test_includes_builtin_from_settings(self, tmp_aia, tmp_settings_json, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_aia.parent)
        monkeypatch.setattr(
            "amanda_ia.tools.registry.get_mcp_tool_schemas",
            lambda _: [],  # Sin MCP para aislar
        )

        tools = registry.get_tools(None)
        # settings tiene get_time enabled
        assert len(tools) >= 1
