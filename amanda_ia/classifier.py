"""Clasificador LLM: determina qué MCPs cargar según el prompt del usuario."""

from __future__ import annotations

import json
import os
from typing import Any

from ollama import chat as ollama_chat

# Modelo ligero por defecto: clasificación es tarea simple, no necesita el modelo principal
CLASSIFIER_MODEL = os.environ.get("AIA_CLASSIFIER_MODEL", "llama3.2:3b")
FALLBACK_MODEL = os.environ.get("AIA_OLLAMA_MODEL", "llama3.1:8b")

CLASSIFIER_PROMPT = """Analiza el mensaje del usuario y devuelve SOLO un JSON con los nombres de los servidores MCP relevantes.

{server_rules}

IMPORTANTE: Si es saludo (hola, buenos días), conversación general o no coincide con ninguna categoría, devuelve [] (array vacío).
Solo incluye servidores cuando el mensaje claramente pida algo de esa categoría.

Responde ÚNICAMENTE con un JSON array, ej: [] o ["wahapedia"] o ["filesystem", "temperatura"]."""


def classify_prompt(message: str, servers: list[dict[str, Any]]) -> list[str]:
    """
    Clasifica el prompt y retorna los nombres de MCP a cargar.
    servers: lista de dicts con name y opcional keywords (desde .aia/mcp.json).
    """
    if not servers:
        return []

    server_names = [s.get("name") for s in servers if s.get("name")]
    rules = []
    for s in servers:
        name = s.get("name")
        if not name:
            continue
        kw = s.get("keywords", [])
        kw_str = ", ".join(kw) if isinstance(kw, list) else str(kw)
        rules.append(f"- {name}: {kw_str or 'sin keywords'}")
    server_rules = "Reglas (keywords por servidor):\n" + "\n".join(rules) if rules else f"Servidores: {', '.join(server_names)}"

    prompt = CLASSIFIER_PROMPT.format(server_rules=server_rules)

    models = [CLASSIFIER_MODEL]
    if FALLBACK_MODEL != CLASSIFIER_MODEL:
        models.append(FALLBACK_MODEL)
    for model in models:
        try:
            response = ollama_chat(
                model=model,
                messages=[{"role": "user", "content": f"Mensaje: {message}\n\n{prompt}"}],
            )
            content = (getattr(response.message, "content", None) or "").strip()

            # Extraer JSON del contenido (puede venir con markdown o texto extra)
            content = content.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(content)
            if isinstance(parsed, list):
                # Validar que los nombres existan
                return [s for s in parsed if isinstance(s, str) and s in server_names]
            return []  # Respuesta inválida: no cargar MCP
        except Exception:
            continue
    return server_names  # Fallo técnico (ej. modelo no disponible): cargar todos
