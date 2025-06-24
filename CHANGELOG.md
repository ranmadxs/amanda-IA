## [0.10.0] - 2024-06-23
### Added/Changed/Fixed
- ✨ Extracción y guardado de archivos .md y .json en target/wh40k
- 🛡️ Robustez en el manejo de clasificación y generación de URL en WahapediaSvC
- 🧪 Tests de Wahapedia ahora aceptan None como respuesta para casos no clasificables
- 🧹 Limpieza y organización automática de archivos de resultados

## [0.9.0] - YYYY-MM-DD
### Added
- Nueva dependencia `html2text` para conversión de HTML a Markdown.
- Nuevo método `_html_to_markdown_html2text` en `HTMLExtractor` para una mejor conversión a Markdown.
- Guardado automático de los resultados de conversión a Markdown en la carpeta `target/`.
- Nuevo método `explain_stats_natural_language` para explicar las estadísticas de Wahapedia en lenguaje natural.
- Nuevo método `classify_user_message_section` en `WahapediaSvC` para clasificar la intención del usuario (estadísticas, armas, estratagemas).

### Changed
- Refactorización del clasificador de secciones en `WahapediaSvC` para que se inicialice en el `__init__` y funcione como singleton, mejorando la eficiencia.
- Mejorados los tests del clasificador con preguntas más realistas y variadas.

### Fixed
- Eliminados imports de librerías de dentro de los métodos, siguiendo las mejores prácticas. 

## [0.8.0] - YYYY-MM-DD
### Added
- Nuevo servicio `MqttCommanderSvc` para manejar comandos MQTT de forma independiente.
- URL de Wahapedia agregada al final de las respuestas de estadísticas (`url={wahapedia_url}`).

### Changed
- Refactorización: Lógica de MQTT movida de `AIAModels` a `MqttCommanderSvc` para mejor separación de responsabilidades.
- Tests actualizados para usar el nuevo servicio MQTT.

### Removed
- Métodos `get_mqtt_command` y `_send_mqtt_async` de `AIAModels` (movidos a `MqttCommanderSvc`).

## [0.7.0] - YYYY-MM-DD
### Added
- Mejora visual del input de texto y alineación de radio buttons para tipo de chat.
- Persistencia del historial de chat usando localStorage.
- Botón pequeño con emoji de escoba 🧹 para borrar el historial de chat.

### Changed
- El formulario de tipo de chat ahora usa radio buttons (solo uno a la vez).
- El endpoint `/status` reemplaza al antiguo `/` para healthcheck. 

## [0.6.2] - 2024-06-21
### Added/Changed/Fixed
- ⬆️ Actualización de dependencia `aia-read-svc` a 0.6.2
- 🧹 Eliminados métodos internos no utilizados en `AIAModels` para mayor claridad
- 🛠️ Mejoras menores de robustez y compatibilidad

## [0.6.1] - 2025-06-20
### Changed
- Refactorización de `get_wahapedia_stats` moviéndolo a `WahapediaSvC` para desacoplar la lógica.
- Movido el test `test_chat_endpoint_wahapedia` a `test_wahapedia_svc.py`.

## [0.6.0] - 2025-06-19
### Added/Changed/Fixed
- ✨ Incremento de versión minor siguiendo el proceso de versionado automatizado.
- ✨ Mejoras en la lógica de clasificación y robustez en la generación de URLs de Wahapedia.

## [0.5.0] - 2024-06-19

### Added
- ✨ Mejoras generales de estabilidad y refactorización de servicios internos.
- ✨ Documentación y scripts de prueba actualizados para facilitar el uso y despliegue.

### Changed
- 🔄 Optimización de la integración con Kafka y Wahapedia.
- 🔄 Refactorización de la arquitectura para mayor mantenibilidad y claridad.

### Fixed
- 🐛 Corrección de errores menores en la API y en los tests unitarios.

## [0.4.2] - 2025-06-18

### Changed
- 🔄 Callback de Kafka en `AIAService` ahora trata el mensaje como string directo, sin validación de estructura.
- 🔄 Daemon usa directamente `AIAService` para la integración con Kafka.
- 🔄 Pruebas básicas de API y tests unitarios exitosas.

### Fixed
- 🐛 Eliminada lógica innecesaria en el callback de Kafka. 

## [0.4.1] - 2025-06-18

### Changed
- 🔄 **Refactorización mayor del código** - Eliminación completa de duplicaciones
- 🔄 **Centralización de lógica** - Toda la lógica de procesamiento movida a `ai_models.py`
- 🔄 **Simplificación de API** - Daemon y tests ahora solo pasan strings al servicio
- 🔄 **Nuevo método `chat()`** - API simplificada que recibe solo `user_message: str`
- 🔄 **Métodos privados organizados** - Lógica separada en métodos específicos:
  - `_get_system_message_with_date()` - Contexto con fecha
  - `_detect_and_extract_urls()` - Procesamiento de URLs
  - `_create_system_message_with_urls()` - Contexto para URLs
  - `_create_messages_for_model()` - Orquestación de mensajes
  - `_generate_response_internal()` - Generación interna

### Removed
- 🗑️ **Duplicaciones eliminadas** - Lógica de fecha, URLs y extracción HTML centralizada
- 🗑️ **Imports innecesarios** - transformers, torch, requests, bs4 removidos del daemon
- 🗑️ **Código duplicado** - Función `get_system_message()` removida de tests
- 🗑️ **Lógica redundante** - Detección de URLs y creación de contexto simplificada

### Fixed
- 🐛 **Mantenibilidad mejorada** - Cambios solo necesarios en un lugar
- 🐛 **Compatibilidad preservada** - Método `generate_response()` mantiene funcionalidad legacy
- 🐛 **Tests simplificados** - Sin lógica duplicada, solo llamadas a `ai_models.chat()`

## [0.4.0] - 2025-01-27

### Added
- ✨ Documentación completa con ejemplos de API y scripts de prueba
- ✨ Scripts ejecutables para testing rápido y completo
- ✨ README.md mejorado con formato moderno y casos de uso
- ✨ Estructura de documentación organizada en `resources/docs/`

### Changed
- 🔄 README.md completamente rediseñado con formato moderno y emojis
- 🔄 Documentación estructurada en carpeta `resources/docs/`
- 🔄 Scripts de prueba automatizados y ejecutables

### Fixed
- 🐛 Código optimizado sin archivos de debug residuales
- 🐛 Tests funcionando al 100% con validación robusta

## [0.3.3] - 2025-01-27

### Changed
- 🔄 Código optimizado: eliminada funcionalidad de debug que guardaba archivos HTML
- 🔄 Mejor rendimiento: menos operaciones de I/O innecesarias

### Fixed
- 🐛 Limpieza de código: eliminados archivos residuales de debug

## [0.3.2] - 2025-01-27

### Added
- ✨ Todos los tests pasando al 100%
- ✨ Corrección del test de extracción HTML para validar contenido flexible

### Changed
- 🔄 Mejorado el test `test_html_content` para validar contenido útil sin depender de elementos HTML específicos
- 🔄 Validación robusta de largo mínimo y patrones de contenido

### Fixed
- 🐛 Corregido test que fallaba al buscar elementos HTML específicos en contenido Markdown

## [0.3.1] - 2025-01-27

### Changed
- 🔼 Incremento de versión patch y ajustes menores en la extracción de estadísticas Wahapedia

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2025-06-18

### Added
- ✨ Integración con Wahapedia para extracción y análisis de contenido
- ✨ Conversión automática de HTML a Markdown para mejor procesamiento
- ✨ Detección automática de URLs de Wahapedia en mensajes del usuario
- ✨ Extracción de estadísticas clave (M, T, Sv, W, Ld, OC) de contenido de Wahapedia
- ✨ Tests unitarios para el endpoint de chat con análisis de Wahapedia

### Changed
- 🔄 Renombrado método `get_html_content` a `get_wahapedia_content` para mayor claridad
- 🔄 Mejora en el prompt del modelo para extracción precisa de estadísticas
- 🔄 Optimización del procesamiento de contenido web

### Fixed
- 🐛 Corrección en la extracción de contenido específico de Wahapedia (dsBannerWrap)
- 🐛 Mejora en el manejo de respuestas del modelo para evitar invención de datos

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
 

