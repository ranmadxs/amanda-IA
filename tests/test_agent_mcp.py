"""Tests de comandos /mcp y keyword fallback en el agente."""

import json
import re

import pytest

from amanda_ia.agent import _keyword_fallback, _run_mcp_command, process


class TestMcpCommand:
    """Tests para /mcp list y /mcp <name> disabled|enabled."""

    def test_mcp_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text('{"servers": []}', encoding="utf-8")

        result = _run_mcp_command(["/mcp", "list"])
        assert "No hay servidores MCP" in result

    def test_mcp_list_with_servers(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text(
            json.dumps({
                "servers": [
                    {"name": "temperatura", "url": "http://localhost:8001/mcp", "keywords": ["clima"]},
                    {"name": "filesystem", "command": "npx", "args": ["-y", "fs"], "enabled": False},
                ]
            }, indent=2),
            encoding="utf-8",
        )

        result = _run_mcp_command(["/mcp", "list"])
        assert "temperatura" in result
        assert "filesystem" in result
        assert "HTTP" in result
        assert "stdio" in result
        assert "enabled" in result
        assert "disabled" in result

    def test_mcp_disable_server(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        monkeypatch.setattr("amanda_ia.mcp_client.invalidate_mcp_cache", lambda: None)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text(
            json.dumps({"servers": [{"name": "temperatura", "url": "http://localhost:8001/mcp"}]}, indent=2),
            encoding="utf-8",
        )

        result = _run_mcp_command(["/mcp", "temperatura", "disabled"])
        assert "deshabilitado" in result

        data = json.loads((tmp_path / ".aia" / "mcp.json").read_text(encoding="utf-8"))
        assert data["servers"][0]["enabled"] is False

    def test_mcp_enable_server(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        monkeypatch.setattr("amanda_ia.mcp_client.invalidate_mcp_cache", lambda: None)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text(
            json.dumps({"servers": [{"name": "temperatura", "url": "http://x", "enabled": False}]}, indent=2),
            encoding="utf-8",
        )

        result = _run_mcp_command(["/mcp", "temperatura", "enabled"])
        assert "habilitado" in result

        data = json.loads((tmp_path / ".aia" / "mcp.json").read_text(encoding="utf-8"))
        assert data["servers"][0]["enabled"] is True

    def test_mcp_disable_nonexistent(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text('{"servers": []}', encoding="utf-8")

        result = _run_mcp_command(["/mcp", "inexistente", "disabled"])
        assert "No existe" in result

    def test_mcp_usage_help(self):
        result = _run_mcp_command(["/mcp"])
        assert "Uso" in result

    def test_process_mcp_list(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text(
            json.dumps({"servers": [{"name": "test", "url": "http://x"}]}, indent=2),
            encoding="utf-8",
        )

        result = process("/mcp list")
        assert "test" in result
        assert "MCP servidores" in result


class TestKeywordFallback:
    """Fallback por keywords cuando el clasificador devuelve []."""

    def test_carpeta_lista_contenido_matches_filesystem(self):
        servers = [
            {"name": "filesystem", "keywords": ["archivo", "carpeta", "listar", "lista", "contenido"]},
            {"name": "tinaja", "keywords": ["litros", "agua"]},
        ]
        result = _keyword_fallback("lista el contenido de la carpeta actual", servers)
        assert "filesystem" in result

    def test_litros_agua_matches_tinaja(self):
        servers = [
            {"name": "filesystem", "keywords": ["carpeta"]},
            {"name": "tinaja", "keywords": ["tinaja", "litros", "agua", "capacidad"]},
        ]
        result = _keyword_fallback("¿Cuántos litros de agua hay disponibles?", servers)
        assert "tinaja" in result

    def test_saludo_no_match(self):
        servers = [{"name": "filesystem", "keywords": ["carpeta", "lista"]}]
        result = _keyword_fallback("Hola, buenos días", servers)
        assert result == []

    def test_no_keyword_no_match(self):
        """Sin keywords coincidentes no activa fallback."""
        servers = [{"name": "filesystem", "keywords": ["carpeta", "lista"]}]
        result = _keyword_fallback("hola qué tal", servers)
        assert result == []

    def test_litros_solo_matches_tinaja(self):
        """'litros disponibles' con 1 keyword activa tinaja (fallback)."""
        servers = [{"name": "tinaja", "keywords": ["litros", "agua", "capacidad"]}]
        result = _keyword_fallback("¿Cuántos litros disponibles hay?", servers)
        assert "tinaja" in result


class TestTimeQueryBypass:
    """Consultas de hora/fecha no cargan MCP (solo get_time)."""

    def test_hora_bypass_uses_only_builtin(self, tmp_path, monkeypatch):
        """'dime la hora' hace bypass: no clasificador, no MCP, solo get_time."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mcp.json").write_text(
            json.dumps({"servers": [{"name": "mongodb", "command": "npx", "args": ["-y", "mongodb-mcp-server"]}]}, indent=2),
            encoding="utf-8",
        )
        mcp_schemas_called_with = []

        def capture_mcp_schemas(server_names):
            mcp_schemas_called_with.append(server_names)
            return []

        monkeypatch.setattr("amanda_ia.tools.registry.get_mcp_tool_schemas", capture_mcp_schemas)
        monkeypatch.setattr("amanda_ia.agent.ollama_chat", lambda **kw: type("R", (), {"message": type("M", (), {"content": "04:20:00 - 19/03/2026", "tool_calls": None})()})())

        result = process("dime la hora actual")
        assert "04:20" in result or "hora" in result.lower()
        assert mcp_schemas_called_with == []


class TestGetTimeIntegration:
    """Test de integración: pregunta la hora al modelo y valida que la respuesta incluya hora."""

    @pytest.mark.ollama
    def test_que_hora_es_devuelve_hora_en_respuesta(self, tmp_path, monkeypatch):
        """Simula aia -m 'qué hora es': la respuesta debe contener un patrón de hora (HH:MM o HH:MM:SS)."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "settings.json").write_text(
            json.dumps({"tools": [{"name": "get_time", "enabled": True}]}),
            encoding="utf-8",
        )
        (tmp_path / ".aia" / "mcp.json").write_text('{"servers": []}', encoding="utf-8")

        response = process("qué hora es")
        assert response, "Respuesta vacía"
        assert not response.startswith("[dim red]Error"), f"Error del modelo: {response[:200]}"

        # Patrón hora: HH:MM o HH:MM:SS (ej: 04:20, 14:30:05)
        time_pattern = re.compile(r"\d{1,2}:\d{2}(:\d{2})?")
        assert time_pattern.search(response), (
            f"La respuesta debe contener una hora (HH:MM o HH:MM:SS). Obtuvo: {response[:150]}..."
        )
