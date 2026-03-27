# Testing por SSH

## Setup

El proyecto vive en el servidor `ranmadxs` (ver `~/.ssh/config`):

```
Host ranmadxs
    HostName 192.168.1.45
    User ranmadxs
    IdentityFile ~/.ssh/id_ranmadxs
```

El filesystem del servidor está montado localmente en `/Volumes/ranmadxs/`, por lo que editar archivos en `/Volumes/ranmadxs/trabajos/amanda-IA/` y en `~/trabajos/amanda-IA/` (desde el servidor) es equivalente.

Poetry está en `~/.local/bin/poetry` en el servidor (no en PATH por defecto en sesiones no-interactivas).

---

## Correr tests

```bash
ssh ranmadxs 'cd ~/trabajos/amanda-IA && ~/.local/bin/poetry run pytest tests/test_agent_mcp.py -q --no-header -m "not ollama"'
```

- `-m "not ollama"` excluye tests que requieren Ollama corriendo
- Resultado esperado: `27 passed, 1 deselected`

### Con Ollama activo

```bash
ssh ranmadxs 'cd ~/trabajos/amanda-IA && ~/.local/bin/poetry run pytest tests/test_agent_mcp.py -q --no-header'
```

- Resultado esperado: `28 passed`

### Un test específico

```bash
ssh ranmadxs 'cd ~/trabajos/amanda-IA && ~/.local/bin/poetry run pytest tests/test_agent_mcp.py::NombreClase::nombre_test -v'
```

---

## Instalar dependencias nuevas

```bash
ssh ranmadxs 'cd ~/trabajos/amanda-IA && ~/.local/bin/poetry install --with dev'
```

---

## Notas

- Claude Code corre localmente en el Mac, pero el entorno Python correcto está en el servidor SSH.
- No usar `python -m pytest` directamente desde el Mac — el entorno fury_venv no tiene pytest del proyecto.
- El comando `ssh ranmadxs '...'` es la forma canónica de ejecutar cualquier comando del proyecto.
