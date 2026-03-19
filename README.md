# Amanda-IA

Agente IA tipo Claude Code. Proyecto base para ir agregando funcionalidades.

## Instalación

```bash
poetry install
```

## Uso

```bash
poetry run aia
```

## Configuración

- **`.aia/mcp.json`** — Servidores MCP (temperatura, wahapedia, filesystem, etc.)
- **`.aia/settings.json`** — Tools builtin habilitadas (get_temperature, get_time, etc.)

Para levantar los servidores MCP (proyecto hermano [aia-mcp](../aia-mcp)):

```bash
cd aia-mcp && poetry run mcp all --http
```

## Ejemplos de preguntas

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

### Sistema de archivos

- *Lista el contenido de la carpeta actual*
- *¿Qué hay en el directorio src?*
- *Lee el archivo README.md*
- *Busca archivos que contengan "test" en el nombre*
- *Crea la carpeta docs/ejemplos*
