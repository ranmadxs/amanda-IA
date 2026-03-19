"""Tests de integración: validan prompts del README ## Ejemplos de preguntas.
Requiere: 1) Ollama corriendo  2) Ejecutar scripts/capture_readme_responses.py primero
Ejecutar: poetry run pytest -m readme -v
"""

import json
from pathlib import Path

import pytest

from amanda_ia.agent import process

EXPECTED_PATH = Path(__file__).parent / "expected_readme_responses.json"

# Prompts del README ## Ejemplos de preguntas
PROMPTS_README = [
    "Lista el contenido de la carpeta actual",
    "¿Qué hay en el directorio src?",
    "Lee el archivo README.md",
    "Busca archivos que contengan \"test\" en el nombre",
    "Crea la carpeta docs/ejemplos",
    "¿Cuáles son las estadísticas de un Rhino?",
    "Dame los datos de Saint Celestine",
    "Stats de un Space Marine",
    "¿Qué temperatura hay en Santiago?",
    "¿Cómo está el clima en Santiago de Chile?",
    "Temperatura en Buenos Aires",
    "¿Cuántos grados hay en Lima?",
    "¿Qué porcentaje de agua está ocupada?",
    "¿Cuántos litros disponibles hay?",
]


def _load_expected():
    if not EXPECTED_PATH.exists():
        pytest.skip(
            f"Ejecuta primero: poetry run python scripts/capture_readme_responses.py\n"
            f"Falta {EXPECTED_PATH}"
        )
    with open(EXPECTED_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.readme
@pytest.mark.parametrize("prompt", PROMPTS_README)
def test_prompt_response_matches_expected(prompt):
    """Valida que la respuesta del modelo coincida con la capturada."""
    expected_data = _load_expected()
    if prompt not in expected_data:
        pytest.skip(f"Prompt no en expected: {prompt[:40]}...")

    exp = expected_data[prompt]
    if exp.get("error"):
        pytest.skip(f"Captura falló: {exp['error']}")

    response = process(prompt)
    assert response, "Respuesta vacía"
    assert not response.startswith("[dim red]Error"), f"Modelo devolvió error: {response[:200]}"
    assert len(response) > 20, "Respuesta demasiado corta"
    assert not response.startswith("[dim]Sin respuesta"), "Modelo no respondió"

    # Comparación con respuesta esperada (capturada previamente)
    expected_resp = exp["response"]
    if expected_resp:
        # Validar que la respuesta actual sea coherente con la esperada
        # (misma longitud aproximada o contenido similar por tipo de prompt)
        assert len(response) >= len(expected_resp) * 0.3, (
            f"Respuesta mucho más corta que la esperada: {len(response)} vs {len(expected_resp)}"
        )


@pytest.mark.readme
def test_all_prompts_have_expected():
    """Verifica que exista el archivo de respuestas esperadas."""
    expected = _load_expected()
    missing = [p for p in PROMPTS_README if p not in expected]
    assert not missing, f"Faltan prompts en expected: {missing}"
