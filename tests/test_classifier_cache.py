"""Tests del cache de clasificación."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from amanda_ia.classifier_cache import get, set_, delete_all, _get_ttl_hours


def test_get_set_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("amanda_ia.classifier_cache._cache_path", lambda: tmp_path / "classifier.json")
    monkeypatch.setattr("amanda_ia.classifier_cache._get_ttl_hours", lambda: 6.0)

    set_("hola", [])
    assert get("hola") == []

    set_("¿Qué bases de datos hay?", ["mongodb"])
    assert get("¿Qué bases de datos hay?") == ["mongodb"]


def test_delete_all(tmp_path, monkeypatch):
    monkeypatch.setattr("amanda_ia.classifier_cache._cache_path", lambda: tmp_path / "classifier.json")
    monkeypatch.setattr("amanda_ia.classifier_cache._get_ttl_hours", lambda: 6.0)

    set_("hola", [])
    assert get("hola") == []

    delete_all()
    assert get("hola") is None
    assert not (tmp_path / "classifier.json").exists()


def test_ttl_from_settings(tmp_aia, monkeypatch):
    monkeypatch.setattr("amanda_ia.classifier_cache._project_root", lambda: tmp_aia.parent)
    (tmp_aia / "settings.json").write_text(
        json.dumps({"tools": [], "classifierCache": {"ttlHours": 12}}),
        encoding="utf-8",
    )
    assert _get_ttl_hours() == 12.0
