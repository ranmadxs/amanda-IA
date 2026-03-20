"""Tests de prompts: simulan aia -m '<mensaje>' y validan la respuesta."""

import re

import pytest

from amanda_ia.agent import process


# Schema y mock para get_temperature (evita conectar a MCP real)
_FAKE_TEMP_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_temperature",
        "description": "Obtiene la temperatura de una ciudad.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
    },
}
_FAKE_TEMP_SERVER = {"name": "temperatura", "url": "http://localhost:8001/mcp"}


def _mock_fetch_server_tools(server_names=None):
    """Mock: devuelve get_temperature sin conectar a MCP."""
    tool_map = {"get_temperature": _FAKE_TEMP_SERVER}
    schemas = [_FAKE_TEMP_SCHEMA]
    if server_names and "temperatura" not in server_names:
        return {}, []
    return tool_map, schemas


def _mock_call_mcp_tool(name: str, arguments: dict) -> str | None:
    """Mock: get_temperature devuelve 22°C para Santiago."""
    if name == "get_temperature":
        city = (arguments.get("city") or "").strip().lower()
        if "santiago" in city or not city:
            return "22°C"
        return "21°C"
    return None


class TestTemperaturaPrompt:
    """Test de integración: temperatura en Santiago."""

    @pytest.mark.ollama
    def test_temperatura_santiago_devuelve_temperatura(self, tmp_path, monkeypatch):
        """Simula aia -m 'que temperatura hay en santiago?': la respuesta debe contener Santiago y temperatura en °C."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        monkeypatch.setattr("amanda_ia.mcp_client._fetch_server_tools", _mock_fetch_server_tools)
        monkeypatch.setattr("amanda_ia.mcp_client.call_mcp_tool", _mock_call_mcp_tool)
        monkeypatch.setattr("amanda_ia.mcp_client._tool_map_cache", None)
        monkeypatch.setattr("amanda_ia.mcp_client._schemas_cache", None)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "settings.json").write_text(
            '{"tools": [{"name": "get_time", "enabled": true}]}',
            encoding="utf-8",
        )
        (tmp_path / ".aia" / "mcp.json").write_text(
            """{
                "servers": [{
                    "name": "temperatura",
                    "url": "http://localhost:8001/mcp",
                    "keywords": ["temperatura", "clima", "ciudad", "tiempo", "grados", "°C"]
                }]
            }""",
            encoding="utf-8",
        )

        response = process("que temperatura hay en santiago?")
        assert response, "Respuesta vacía"
        assert not response.startswith("[dim red]Error"), f"Error del modelo: {response[:200]}"

        response_lower = response.lower()
        assert "santiago" in response_lower, (
            f"La respuesta debe mencionar Santiago. Obtuvo: {response[:150]}..."
        )

        # Temperatura: °C, grados, o número (ej: 18, 22, 18.5)
        has_temp = (
            "°c" in response_lower
            or "°" in response
            or "grados" in response_lower
            or re.search(r"\d+\s*°", response)
            or re.search(r"\b\d{1,2}(?:\.\d+)?\b", response)
        )
        assert has_temp, (
            f"La respuesta debe incluir temperatura (ej: 18, 22°C). Obtuvo: {response[:150]}..."
        )
