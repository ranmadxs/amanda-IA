# Specs MCP para aia

Este directorio contiene **especificaciones** para servidores MCP. Los servidores se implementan en un proyecto separado: **aia-mcp** (un nivel arriba de amanda-IA).

## Ubicación del proyecto MCP

```
trabajos/
├── amanda-IA/    # Este proyecto (agente aia)
│   └── mcp/      # Specs (este directorio)
└── aia-mcp/      # Proyecto donde se implementan los servidores MCP
    └── temperatura/
        └── server.py
```

## Estructura en aia-mcp

Cada servidor vive en su propio directorio dentro de `aia-mcp/`:

```
aia-mcp/
├── README.md
├── pyproject.toml
└── temperatura/
    ├── __init__.py
    └── server.py
```

## Cómo usar las specs

Los archivos `SPEC_*.md` son especificaciones para que otra IA implemente los servidores. Cada spec describe:

- Tool(s) a exponer
- Parámetros y retornos
- Stack técnico
- Cómo ejecutar

## Servidores planeados

| Servidor    | Spec                  | Tool(s)          |
|-------------|------------------------|------------------|
| temperatura | SPEC_TEMPERATURA.md    | get_temperature  |
