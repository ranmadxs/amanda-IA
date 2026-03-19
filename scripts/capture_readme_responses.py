#!/usr/bin/env python3
"""Captura respuestas del modelo para los prompts del README.
Ejecutar: poetry run python scripts/capture_readme_responses.py
Genera tests/expected_readme_responses.json para validar en tests.
"""

import json
import sys
from pathlib import Path

# Añadir raíz del proyecto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from amanda_ia.agent import process

PROMPTS = [
    # Sistema de archivos
    "Lista el contenido de la carpeta actual",
    "¿Qué hay en el directorio src?",
    "Lee el archivo README.md",
    "Busca archivos que contengan \"test\" en el nombre",
    "Crea la carpeta docs/ejemplos",
    # Warhammer 40K
    "¿Cuáles son las estadísticas de un Rhino?",
    "Dame los datos de Saint Celestine",
    "Stats de un Space Marine",
    # Temperatura
    "¿Qué temperatura hay en Santiago?",
    "¿Cómo está el clima en Santiago de Chile?",
    "Temperatura en Buenos Aires",
    "¿Cuántos grados hay en Lima?",
    # Tinaja
    "¿Qué porcentaje de agua está ocupada?",
    "¿Cuántos litros disponibles hay?",
]


def main():
    root = Path(__file__).resolve().parent.parent
    out_path = root / "tests" / "expected_readme_responses.json"

    results = {}
    for i, prompt in enumerate(PROMPTS):
        print(f"[{i+1}/{len(PROMPTS)}] {prompt[:50]}...")
        try:
            response = process(prompt)
            results[prompt] = {"response": response, "error": None}
        except Exception as e:
            results[prompt] = {"response": None, "error": str(e)}
        print("  ->", "OK" if results[prompt]["error"] is None else "ERROR")

    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nGuardado en {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
