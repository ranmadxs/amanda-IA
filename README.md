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

## Cómo funcionan las tools

**Por defecto** (sin configurar nada): aia usa tools **builtin** (temperatura, hora) que viven en el propio proyecto. **No necesitas levantar ningún servidor** — funciona solo.

**Con MCP** (opcional): si quieres que las tools vengan de un servidor remoto (aia-mcp):

1. Levanta el servidor MCP en otra terminal:
   ```bash
   cd aia-mcp && poetry run mcp temperatura --http
   ```

2. Crea un `.env` en la raíz del proyecto (o exporta la variable):
   ```
   MCP_URL=http://localhost:8001/mcp
   ```

3. Ejecuta aia:
   ```bash
   poetry run aia
   ```

Si MCP_URL está definido pero el servidor no está levantado, aia hace **fallback** a las tools builtin (sigue funcionando). Cuando se conecta al MCP, el header muestra "Ollama + \<nombre del servidor\>" (ej: "Ollama + temperatura 1.26.0").
