"""Tests del clasificador LLM (README: ejemplos de preguntas -> MCPs)."""

from unittest.mock import patch, MagicMock

import pytest

from amanda_ia.classifier import classify_prompt


class TestClassifyPrompt:
    """Clasificador: mensaje -> nombres de servidores MCP relevantes."""

    def test_empty_servers_returns_empty(self):
        result = classify_prompt("hola", [])
        assert result == []

    def test_warhammer_returns_wahapedia(self):
        """README: ¿Cuáles son las estadísticas de un Rhino? -> wahapedia."""
        servers = [
            {"name": "wahapedia", "keywords": ["warhammer", "40k", "estadísticas", "rhino"]},
            {"name": "temperatura", "keywords": ["temperatura", "clima"]},
        ]
        with patch("amanda_ia.classifier.ollama_chat") as mock_chat:
            mock_chat.return_value = MagicMock(
                message=MagicMock(content='["wahapedia"]')
            )
            result = classify_prompt("¿Cuáles son las estadísticas de un Rhino?", servers)
        assert result == ["wahapedia"]

    def test_temperatura_returns_temperatura(self):
        """README: ¿Qué temperatura hay en Santiago? -> temperatura."""
        servers = [
            {"name": "temperatura", "keywords": ["temperatura", "clima", "ciudad"]},
            {"name": "wahapedia", "keywords": ["warhammer"]},
        ]
        with patch("amanda_ia.classifier.ollama_chat") as mock_chat:
            mock_chat.return_value = MagicMock(
                message=MagicMock(content='["temperatura"]')
            )
            result = classify_prompt("¿Qué temperatura hay en Santiago?", servers)
        assert result == ["temperatura"]

    def test_saludo_returns_empty(self):
        """README: saludo -> [] (no tools)."""
        servers = [{"name": "temperatura", "keywords": ["temperatura"]}]
        with patch("amanda_ia.classifier.ollama_chat") as mock_chat:
            mock_chat.return_value = MagicMock(
                message=MagicMock(content="[]")
            )
            result = classify_prompt("Hola, buenos días", servers)
        assert result == []

    def test_multiple_servers(self):
        """README: puede devolver varios, ej: filesystem + temperatura."""
        servers = [
            {"name": "filesystem", "keywords": ["archivo", "carpeta"]},
            {"name": "temperatura", "keywords": ["temperatura"]},
        ]
        with patch("amanda_ia.classifier.ollama_chat") as mock_chat:
            mock_chat.return_value = MagicMock(
                message=MagicMock(content='["filesystem", "temperatura"]')
            )
            result = classify_prompt("lista archivos y dame la temperatura", servers)
        assert "filesystem" in result
        assert "temperatura" in result

    def test_invalid_names_filtered(self):
        """Solo incluye nombres que existen en servers."""
        servers = [{"name": "wahapedia", "keywords": ["warhammer"]}]
        with patch("amanda_ia.classifier.ollama_chat") as mock_chat:
            mock_chat.return_value = MagicMock(
                message=MagicMock(content='["wahapedia", "inexistente"]')
            )
            result = classify_prompt("estadísticas de Rhino", servers)
        assert result == ["wahapedia"]
