# Amanda-IA QwenLM API

Este proyecto expone una API básica usando FastAPI para servir modelos QwenLM (o cualquier modelo compatible con HuggingFace Transformers y JAX/Flax).

## Requisitos
- Python 3.11 o 3.12
- [Poetry](https://python-poetry.org/)

## Instalación

```bash
poetry install
```

## Levantar la API

```bash
poetry run python -m amanda_ia.daemon
```

La API estará disponible en: http://localhost:8000/

## Endpoint de prueba

- `GET /`  
  Responde con un mensaje de prueba para verificar que la API está funcionando.

## Notas
- Si quieres servir un modelo QwenLM, deberás agregar endpoints y lógica para cargar el modelo y procesar requests.
- Actualmente, el proyecto está limpio de dependencias de PyTorch y solo usa JAX/Flax. 