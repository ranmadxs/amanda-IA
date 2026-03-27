"""Tests de comandos /mcp y keyword fallback en el agente."""

import json
import re
from pathlib import Path

import pytest

import amanda_ia.agent as agent_mod
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
        # Solo servidores activos (sin modo) se muestran; filesystem está disabled → oculto
        assert "temperatura" in result
        assert "filesystem" not in result
        assert "🟢" in result

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
        assert "MCP activos" in result


class TestModeCommand:
    """Tests de /mod y activación de modo visual."""

    def _write_mods(self, tmp_path, modes: list):
        (tmp_path / ".aia").mkdir(exist_ok=True)
        (tmp_path / ".aia" / "mods.json").write_text(
            json.dumps({"mods": modes}, indent=2), encoding="utf-8"
        )

    def test_modo_lists_available_modes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        self._write_mods(tmp_path, [
            {"name": "warhammer", "key": "modo_warhammer", "color": "#9b59b6", "enabled": True},
            {"name": "monitor", "key": "modo_monitor", "color": "#3498db", "enabled": True},
        ])
        (tmp_path / ".aia" / "mcp.json").write_text('{"servers": []}', encoding="utf-8")

        result = process("/mod")
        assert "Modos disponibles" in result
        assert "warhammer" in result
        assert "monitor" in result

    def test_mod_list_shows_disabled_modes(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        self._write_mods(tmp_path, [
            {"name": "warhammer", "key": "modo_warhammer", "color": "#9b59b6", "enabled": False},
        ])
        (tmp_path / ".aia" / "mcp.json").write_text('{"servers": []}', encoding="utf-8")

        result = process("/mod list")
        assert "warhammer" in result
        assert "disabled" in result

    def test_mod_enable_disable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        self._write_mods(tmp_path, [
            {"name": "warhammer", "key": "modo_warhammer", "color": "#9b59b6", "enabled": True},
        ])
        (tmp_path / ".aia" / "mcp.json").write_text('{"servers": []}', encoding="utf-8")
        monkeypatch.setattr("amanda_ia.mcp_client.invalidate_mcp_cache", lambda: None)

        result = process("/mod warhammer disabled")
        assert "deshabilitado" in result
        data = json.loads((tmp_path / ".aia" / "mods.json").read_text(encoding="utf-8"))
        assert data["mods"][0]["enabled"] is False

        result = process("/mod warhammer enabled")
        assert "habilitado" in result

    def test_modo_activates_even_if_mode_server_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
        self._write_mods(tmp_path, [
            {"name": "warhammer", "key": "modo_warhammer", "color": "#9b59b6", "enabled": True},
        ])
        (tmp_path / ".aia" / "mcp.json").write_text(
            json.dumps(
                {
                    "servers": [
                        {
                            "name": "wahapedia",
                            "url": "http://localhost:8002/mcp",
                            "modo": "modo_warhammer",
                            "enabled": False,
                        }
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        prev = agent_mod._active_mode
        try:
            result = process("/mod warhammer")
            assert "activado" in result
            assert agent_mod._active_mode == "modo_warhammer"
        finally:
            agent_mod._active_mode = prev


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
    def test_que_hora_es_devuelve_hora_en_respuesta(self, tmp_path, monkeypatch):  # noqa: F811
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


class TestModesInProject:
    """Garantiza que los modos warhammer y monitor existen en los archivos reales del proyecto."""

    PROJECT_ROOT = Path(__file__).parent.parent
    MCP_JSON = PROJECT_ROOT / ".aia" / "mcp.json"
    MODS_JSON = PROJECT_ROOT / ".aia" / "mods.json"

    def _load_mods(self):
        assert self.MODS_JSON.exists(), f"No se encontró {self.MODS_JSON}"
        return json.loads(self.MODS_JSON.read_text(encoding="utf-8")).get("mods", [])

    def _load_servers(self):
        assert self.MCP_JSON.exists(), f"No se encontró {self.MCP_JSON}"
        return json.loads(self.MCP_JSON.read_text(encoding="utf-8")).get("servers", [])

    def test_mods_json_has_warhammer(self):
        """Debe existir modo warhammer en .aia/mods.json."""
        mods = self._load_mods()
        keys = {m.get("key") for m in mods}
        assert "modo_warhammer" in keys, "No hay modo_warhammer en .aia/mods.json"

    def test_mods_json_has_monitor(self):
        """Debe existir modo monitor en .aia/mods.json."""
        mods = self._load_mods()
        keys = {m.get("key") for m in mods}
        assert "modo_monitor" in keys, "No hay modo_monitor en .aia/mods.json"

    def test_mcp_json_has_warhammer_mode(self):
        """Debe existir al menos un server con modo_warhammer en .aia/mcp.json."""
        servers = self._load_servers()
        modos = {s.get("modo") for s in servers}
        assert "modo_warhammer" in modos, "No hay ningún server con modo_warhammer en .aia/mcp.json"

    def test_mcp_json_has_monitor_mode(self):
        """Debe existir al menos un server con modo_monitor en .aia/mcp.json."""
        servers = self._load_servers()
        modos = {s.get("modo") for s in servers}
        assert "modo_monitor" in modos, "No hay ningún server con modo_monitor en .aia/mcp.json"

    def test_mod_warhammer_activates(self, monkeypatch):
        """'/mod warhammer' activa modo_warhammer usando los archivos reales."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: self.PROJECT_ROOT)
        prev = agent_mod._active_mode
        try:
            result = process("/mod warhammer")
            assert "activado" in result, f"Esperaba 'activado', obtuvo: {result}"
            assert agent_mod._active_mode == "modo_warhammer"
        finally:
            agent_mod._active_mode = prev

    def test_mod_monitor_activates(self, monkeypatch):
        """'/mod monitor' activa modo_monitor usando los archivos reales."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: self.PROJECT_ROOT)
        prev = agent_mod._active_mode
        try:
            result = process("/mod monitor")
            assert "activado" in result, f"Esperaba 'activado', obtuvo: {result}"
            assert agent_mod._active_mode == "modo_monitor"
        finally:
            agent_mod._active_mode = prev

    def test_watch_only_visible_in_monitor_mode(self, monkeypatch):
        """/watch aparece en completions solo cuando modo_monitor está activo."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: self.PROJECT_ROOT)
        prev = agent_mod._active_mode
        try:
            agent_mod._active_mode = None
            cmds_general = agent_mod._get_all_slash_commands()
            assert "/watch" not in cmds_general, "/watch no debe aparecer fuera de modo_monitor"

            agent_mod._active_mode = "modo_monitor"
            cmds_monitor = agent_mod._get_all_slash_commands()
            assert "/watch" in cmds_monitor, "/watch debe aparecer en modo_monitor"
        finally:
            agent_mod._active_mode = prev

    def test_help_only_visible_when_mode_active(self, monkeypatch):
        """/help aparece en completions solo cuando hay un modo activo."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: self.PROJECT_ROOT)
        prev = agent_mod._active_mode
        try:
            agent_mod._active_mode = None
            cmds = agent_mod._get_all_slash_commands()
            assert "/help" not in cmds, "/help no debe aparecer sin modo activo"

            agent_mod._active_mode = "modo_warhammer"
            cmds = agent_mod._get_all_slash_commands()
            assert "/help" in cmds, "/help debe aparecer con modo activo"
        finally:
            agent_mod._active_mode = prev

    def test_help_without_mode_returns_hint(self, monkeypatch):
        """/help sin modo activo responde con mensaje orientativo."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: self.PROJECT_ROOT)
        prev = agent_mod._active_mode
        try:
            agent_mod._active_mode = None
            result = process("/help")
            assert "modo" in result.lower(), f"Esperaba mención de 'modo', obtuvo: {result}"
        finally:
            agent_mod._active_mode = prev

    def test_help_calls_get_mode_help_when_mode_active(self, monkeypatch):
        """/help con modo activo llama get_mode_help con el modo correcto."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: self.PROJECT_ROOT)
        called_with = []

        def fake_help(mode_key):
            called_with.append(mode_key)
            return f"help de {mode_key}"

        monkeypatch.setattr("amanda_ia.agent.get_mode_help", fake_help)
        prev = agent_mod._active_mode
        try:
            agent_mod._active_mode = "modo_warhammer"
            result = process("/help")
            assert called_with == ["modo_warhammer"]
            assert "modo_warhammer" in result
        finally:
            agent_mod._active_mode = prev
