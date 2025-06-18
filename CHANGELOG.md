# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-06-18

### Added
- ✨ Nuevo servicio de modelos de IA (`AIAModels`) con soporte para modelos Qwen
- ✨ Servicio de extracción de HTML (`HTMLExtractor`) para procesar contenido web
- ✨ Tests unitarios para modelos de IA y extractor de HTML
- ✨ Configuración de caché local para modelos de Hugging Face
- ✨ Soporte para modo offline en modelos de IA

### Changed
- 🔄 Refactorización de la arquitectura de servicios
- 🔄 Mejora en el manejo de respuestas del modelo (extracción de última respuesta del assistant)
- 🔄 Optimización de la carga de modelos con device mapping automático

### Fixed
- 🐛 Corrección en el manejo de respuestas HTTP y limpieza de HTML
- 🐛 Mejora en el manejo de errores y logging
- 🐛 Corrección de importaciones y estructura de tests

### Removed
- 🗑️ Eliminación del modelo extractor/executor redundante
- 🗑️ Limpieza de archivos de test obsoletos

## [0.1.0] - Initial Release

### Added
- ✨ Implementación inicial del proyecto Amanda-IA
- ✨ API básica de chat con FastAPI
- ✨ Integración con modelos de IA 