## Version 1.4.0 - YYYY-MM-DD
- Añadido nueva característica X.
- Corregido error en módulo Y.# Changelog

Todos los cambios notables del agente amanda-IA se documentan aquí.
El proyecto inició como reescritura en Python en marzo 2026.

---

## [v0.7.1-aia] — 2026-03-22

### Agregado
- **Modo Dev** con MCP integrados: `shell`, `filesystem` y `github` (vía npx `@modelcontextprotocol/server-github`)
- **Etapa de planificación**: el LLM genera el flujo esperado (`MCP(...) -> LLM`) antes de ejecutar, con caché propia (`plan_cache.py`)
- **Logs de llamadas en spinner**: `LLM>>Ollama.<modelo>`, `http>>mcp.<servidor>`, `npx>>mcp.<servidor>`, `sh>>mcp.<servidor>`, `PLAN>><flujo>`
- Comandos slash en modo Dev: `/test`, `/diff`, `/git-log`, `/files`
- `mods.json`: configuración de modos con banner, color, systemPromptExtra y slashCommands
- **Flujo lineal**: reemplazó el `while True` por `LLM con tools → ejecutar MCPs → LLM sin tools → respuesta`
- `exit` siempre cierra la aplicación independientemente del modo activo

### Cambiado
- `_stdio_params()` enriquece el PATH del subproceso con `/opt/homebrew/bin` y `/usr/local/bin` para que `npx` sea encontrado
- `get_server_transport()` determina el prefijo del log: `http`, `npx` o `sh`
- `phase["value"]` ya no se resetea a `""` entre fases — cada fase sobreescribe la anterior evitando spinner vacío
- Respuestas siempre en español; reforzado `SYSTEM_PROMPT_BASE` para modelos como `qwen2.5`

### Corregido
- MCP llamado múltiples veces con paths inventados (eliminado el loop `while True`)
- `npx` no encontrado al lanzar subprocesos MCP stdio en macOS con Homebrew
- Spinner mostrando solo `...` cuando `phase["value"]` quedaba vacío entre fases
- Error "No se cargaron las herramientas MCP" para saludos por caché stale del clasificador

---

## [v0.3.2-alpha.1] — 2026-03-19

### Agregado
- **Clasificador MCP**: LLM clasifica qué servidores MCP necesita el prompt antes de cargarlos
- `settings.json`: TTL de caché, modelo del clasificador, opciones de display
- Spinner braille animado con etiqueta de fase activa
- `cwd` en el prompt de entrada
- `get_tools()` filtra tools por servidores seleccionados

---

## [v0.2.2-alpha.1] — 2026-03-18

### Agregado
- **Integración MCP** (Model Context Protocol): transporte HTTP streamable y stdio (subprocesos)
- Tools builtin: `get_time`, `calculate_tinaja_level`
- Variable de entorno `AIA_OLLAMA_MODEL` para seleccionar modelo Ollama
- `mcp_client.py`: enrutamiento HTTP/stdio, caché de tool map, schemas formato Ollama
- Servidores configurados: MongoDB, temperatura, Wahapedia, monitor

---

## [v0.1.1-alpha.1] — 2026-03-18

### Agregado
- Reescritura completa en Python desde cero
- CLI interactivo con `prompt_toolkit`: input, historial, atajos de teclado
- Renderizado con `rich`: output con formato y colores
- Integración con **Ollama** local (`ollama.chat`)
- Historial de conversación en memoria con compresión automática
- Banners ASCII por modo, prompt con `›` y scroll en output
