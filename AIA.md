# amanda-IA (aia)

Agente de IA conversacional de terminal, construido sobre prompt_toolkit + Ollama. Pensado para correr en una Mac/Linux vía SSH.

## Stack

- **Runtime**: Python 3.11+, poetry
- **UI**: `prompt_toolkit` (TUI full-screen)
- **LLM**: Ollama (modelo configurable via `AIA_OLLAMA_MODEL` en `.env`)
- **Herramientas**: MCP (Model Context Protocol) — servidores stdio y HTTP
- **Dependencias clave**: `mcp`, `rich`, `prompt_toolkit`, `ollama`, `paho-mqtt`

## Estructura

```
amanda_ia/
  agent.py          # Loop principal, UI, key bindings, procesamiento de comandos
  config.py         # Carga settings.json, mcp.json, mods.json
  mcp_client.py     # Cliente MCP: conecta servidores stdio/HTTP, clasifica herramientas
  classifier.py     # Clasifica prompts para decidir qué MCP usar
  classifier_cache.py
  cli.py            # Entrypoint: `aia`
  live_monitor.py   # Monitor MQTT en tiempo real
  tools/            # Herramientas builtin (get_time, etc.)
  resources/        # Banners ASCII art (banner.txt, banner_*.txt)

.aia/
  mcp.json          # Servidores MCP (stdio y HTTP). Campo "modo" vincula al modo activo.
  mods.json         # Modos (warhammer, monitor, dev). Banner, color, systemPromptExtra.
  settings.json     # Configuración del proyecto
  settings.local.json  # Override local (no commitear)
  scripts/
    shell_mcp.py    # MCP server Python para ejecutar comandos (modo dev)

tests/
  test_agent_mcp.py # Tests principales

specs/              # Documentación técnica y decisiones de diseño
```

## Comandos útiles

```bash
# Correr la app
poetry run aia

# Tests (sin Ollama)
~/.local/bin/poetry run pytest tests/ -q --no-header -m "not ollama"

# Tests completos (requiere Ollama corriendo)
~/.local/bin/poetry run pytest tests/ -q --no-header

# Desde Mac via SSH
ssh ranmadxs 'cd ~/trabajos/amanda-IA && ~/.local/bin/poetry run pytest tests/test_agent_mcp.py -q --no-header -m "not ollama"'
```

## Comandos slash de aia

```
/mod list                   # ver modos disponibles
/mod <nombre>               # activar modo
/mod <nombre> disabled      # deshabilitar modo
/mcp list                   # ver servidores MCP
/mcp <nombre> disabled      # deshabilitar MCP
/cache delete               # limpiar caché de clasificación
/flush all|history|ollama   # limpiar conversación / reiniciar
exit | Escape               # salir o desactivar modo
```

## Configuración

- **Modelo Ollama**: variable `AIA_OLLAMA_MODEL` en `.env` (default: `llama3.1:8b`)
- **MCP servers**: `.aia/mcp.json` — agregar `{ "name": "...", "command/url": "..." }`
- **Nuevo modo**: `.aia/mods.json` + crear `amanda_ia/resources/banner_nombre.txt`
- **SSH**: host `ranmadxs`, user `ranmadxs`, ip `192.168.1.45`

## Convenciones

- Todo el código en español (comentarios, nombres de variables de negocio)
- Los tests NO usan mocks para la base de datos (se conectan al real)
- Antes de modificar cualquier archivo: leerlo completo primero
- Después de cambios: correr tests y verificar que pasan
- No usar rutas relativas en MCP filesystem — siempre absolutas

## Lo que NO tocar sin consultar

- `.aia/settings.local.json` — configuración local personal
- `.env` — variables de entorno con secrets
- `mcp_client.py` — lógica de conexión MCP delicada, rompe fácil
