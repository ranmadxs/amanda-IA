"""Fixtures para tests de amanda-IA."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_aia(tmp_path):
    """Directorio .aia en tmp_path para tests aislados."""
    aia = tmp_path / ".aia"
    aia.mkdir()
    return aia


@pytest.fixture
def tmp_mcp_json(tmp_aia):
    """mcp.json vacío en tmp_aia."""
    path = tmp_aia / "mcp.json"
    path.write_text('{"servers": []}', encoding="utf-8")
    return path


@pytest.fixture
def tmp_settings_json(tmp_aia):
    """settings.json con tools en tmp_aia."""
    path = tmp_aia / "settings.json"
    data = {"tools": [{"name": "get_time", "enabled": True}]}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path
