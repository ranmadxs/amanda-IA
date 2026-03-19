# Amanda-IA

Agente IA tipo Claude Code. Proyecto base para ir agregando funcionalidades.

## Instalación

```bash
poetry install
```

## Uso

```bash
cd amanda-IA
poetry run aia
```

> Ejecuta desde el directorio `amanda-IA` para que cargue `.aia/mcp.json`. Si fallan las tools MCP, prueba `/cache delete`.

## Tests

```bash
# Tests unitarios (rápidos)
poetry run pytest

# Tests de prompts (requiere Ollama; temperatura requiere MCP en localhost:8001)
poetry run pytest -m ollama -v

# Tests de prompts del README (requiere Ollama + MCP)
poetry run python scripts/capture_readme_responses.py  # captura respuestas esperadas
poetry run pytest -m readme -v
```

## Configuración

- **`.env`** — `AIA_OLLAMA_MODEL` (chat + tools), `AIA_CLASSIFIER_MODEL` (clasificador MCP, opcional), `AIA_DEBUG=1` (muestra warnings de conexión MCP)
- **`.aia/mcp.json`** — Servidores MCP. Opcional `systemPrompt` por servidor para instrucciones dinámicas.
- **`.aia/settings.json`** — Tools builtin, `classifierCache.ttlHours` (cache de clasificación, default 6)
- **`.aia/cache/`** — Cache persistente: clasificación (se borra con `/cache delete`), wahapedia (config en mcp.json)

**Comandos slash:**
- `/cache delete` — Borra la cache de clasificación
- `/mcp list` — Lista todos los MCP con detalles (tipo, estado, keywords)
- `/mcp <name> disabled` — Deshabilita un MCP (no se considera nunca)
- `/mcp <name> enabled` — Habilita un MCP

Para levantar los servidores MCP (proyecto hermano [aia-mcp](../aia-mcp)):

```bash
cd aia-mcp && poetry run mcp all --http
```

## Ejemplos de preguntas

### Hora (builtin, siempre disponible)

- *¿Qué hora es?*
- *Dame la hora actual*
- *¿Qué día es hoy?*

### Warhammer 40K (Wahapedia)

- *¿Cuáles son las estadísticas de un Rhino?*
- *Dame los datos de Saint Celestine*
- *Stats de un Space Marine*
- *Información de un Carnifex de Tyranids*
- *Estadísticas de Guilliman*

### Temperatura (ciudades de Chile y otras)

- *¿Qué temperatura hay en Santiago?*
- *¿Cómo está el clima en Santiago de Chile?*
- *Temperatura en Buenos Aires*
- *¿Cuántos grados hay en Lima?*

### Tinaja / Acumulador / Estanque (sensor en tiempo real)

- *¿Qué porcentaje de agua está ocupada?*
- *¿Cuántos litros disponibles hay?*
- *¿Cuántos litros hay en el acumulador?*
- *¿Qué porcentaje de agua hay en el acumulador?*
- *¿Me muestras las lecturas en tiempo real de la tinaja?*
- *¿A qué velocidad disminuye el agua?*

> **Lecturas en tiempo real:** El servidor tinaja se conecta a MQTT (mismo broker que monitor_estanque). Variables: `MQTT_HOST`, `MQTT_TOPIC_OUT`, etc. Fallback: `TINAJA_ESTADO_URL` si no hay datos MQTT. Si no hay datos, devuelve un cálculo de ejemplo.

### MongoDB / Base de datos

- *¿Qué bases de datos hay en el cluster?*
- *¿Qué colecciones hay en la base de datos [nombre_db]?*
- *Lista los documentos de la colección X*
- *Inserta un documento en la colección usuarios*
- *Busca en MongoDB los registros que cumplan...*
- *Ejecuta una agregación para contar documentos por categoría*
- *¿Cuál es el esquema de la colección reservas?*

> **Nota:** Para listar colecciones, indica el nombre de la base de datos (ej: `¿Qué colecciones hay en airbnb?`). Si no lo sabes, pregunta primero `¿Qué bases de datos hay?`.

### Sistema de archivos

- *Lista el contenido de la carpeta actual*
- *¿Qué hay en el directorio src?*
- *Lee el archivo README.md*
- *Busca archivos que contengan "test" en el nombre*
- *Crea la carpeta docs/ejemplos*
