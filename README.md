# 🚀 Amanda IA - Chat API.

**Versión actual:** 0.8.0

Este proyecto expone una API avanzada usando FastAPI para servir modelos QwenLM con integración especial para análisis de contenido de Wahapedia.

## ✨ Características Principales

- 🤖 **Modelo IA**: Qwen2-0.5B-Instruct (HuggingFace Transformers)
- 🌐 **Integración Wahapedia**: Extracción automática de estadísticas de unidades
- 📅 **Sistema de Fechas**: Respuestas precisas de fecha actual
- 🔄 **API REST**: Endpoints para chat y análisis de contenido
- 📊 **Extracción de Estadísticas**: M, T, Sv, W, Ld, OC, INVULNERABLE SAVE
- 🎯 **Conversión HTML a Markdown**: Procesamiento optimizado de contenido web

## 📋 Requisitos

- Python 3.11 o 3.12
- [Poetry](https://python-poetry.org/)
- Conexión a internet (para descargar modelos y acceder a Wahapedia)

## 🛠️ Instalación

```bash
# Clonar el repositorio
git clone <repository-url>
cd amanda-IA

# Instalar dependencias
poetry install
```

## 🚀 Levantar la API

```bash
# Iniciar el servicio
poetry run python -m amanda_ia.daemon
```

La API estará disponible en: **http://localhost:8000/**

## 📚 Documentación y Pruebas

### 📖 Documentación Completa
```bash
cat resources/docs/api_examples.md
```

### 🔧 Scripts de Prueba
```bash
# Prueba completa de la API
./resources/docs/test_api.sh

# Prueba rápida
./resources/docs/quick_test.sh
```

## 🎯 Endpoints Disponibles

### Verificar Estado del Servicio
```bash
curl -X GET http://localhost:8000/
```
**Respuesta:** `{"message":"Amanda-IA Chat API is running"}`

### Chat Básico
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hola"}'
```

### Consulta de Fecha
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "que fecha es hoy?"}'
```

### Análisis de Wahapedia
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "analiza https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka"}'
```

## 🎮 Casos de Uso

### Análisis de Unidades de Wahapedia
- **Space Marines**: Lieutenant, Captain, etc.
- **Orks**: Ghazghkull Thraka, Warboss, etc.
- **Necrons**: Overlord, Lord, etc.
- **Y más...**

### Extracción de Estadísticas
El sistema extrae automáticamente:
- **M**: Movimiento
- **T**: Resistencia
- **Sv**: Salva de armadura
- **W**: Heridas
- **Ld**: Liderazgo
- **OC**: Control de objetivo
- **INVULNERABLE SAVE**: Salva invulnerable (si está disponible)

## 🏗️ Arquitectura

```
amanda_ia/
├── daemon.py          # Servidor FastAPI principal
├── models.py          # Modelos Pydantic para requests/responses
├── services/
│   ├── ai_models.py   # Servicio de modelos de IA
│   └── html_extractor.py  # Extractor de contenido HTML
└── tests/             # Tests unitarios
```

## 🧪 Testing

```bash
# Ejecutar todos los tests
poetry run pytest tests/ -v -s

# Tests específicos
poetry run pytest tests/test_ai_models.py -v -s
poetry run pytest tests/test_html_extractor.py -v -s
```

## 📁 Estructura del Proyecto

```
amanda-IA/
├── amanda_ia/         # Código fuente principal
├── tests/             # Tests unitarios
├── resources/         # Recursos del proyecto
│   └── docs/          # Documentación y scripts de prueba
├── pyproject.toml     # Configuración de Poetry
├── CHANGELOG.md       # Historial de cambios
└── README.md          # Este archivo
```

## 🔧 Configuración

### Variables de Entorno
El proyecto usa `python-dotenv` para configuración. Crea un archivo `.env` si necesitas configuraciones específicas.

### Logging
La configuración de logs está en `resources/log_cfg.yaml` y usa `aia-utils` para el manejo de logs.

## 🚀 Despliegue

### Desarrollo Local
```bash
poetry run python -m amanda_ia.daemon
```

### Producción
```bash
# Usar uvicorn directamente
uvicorn amanda_ia.daemon:app --host 0.0.0.0 --port 8000
```

## 📊 Estado del Proyecto

- ✅ **API funcionando** al 100%
- ✅ **Integración Wahapedia** operativa
- ✅ **Tests pasando** (100% de éxito)
- ✅ **Documentación completa**
- ✅ **Scripts de prueba** disponibles

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## 📝 Notas Técnicas

- **Modelo**: Qwen2-0.5B-Instruct (CPU optimizado)
- **Framework**: FastAPI + Uvicorn
- **Procesamiento**: HTML → Markdown → IA Analysis
- **Cache**: HTTP requests con `aia-utils`
- **Logging**: Configurado con `aia-utils.logs_cfg`

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver el archivo `LICENSE` para más detalles.

---

**¡Amanda IA está listo para analizar el universo de Warhammer 40,000!** 🎯 