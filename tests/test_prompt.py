"""Tests de prompts: simulan aia -m '<mensaje>' y validan la respuesta."""

import re

import pytest

from amanda_ia.agent import process


class TestTemperaturaPrompt:
    """Test de integración: temperatura en Santiago."""

    @pytest.mark.ollama
    def test_temperatura_santiago_devuelve_temperatura(self, tmp_path, monkeypatch):
        """Simula aia -m 'que temperatura hay en santiago?': la respuesta debe contener Santiago y temperatura en °C."""
        monkeypatch.setattr("amanda_ia.config._project_root", lambda: tmp_path)
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
