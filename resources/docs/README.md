# 📚 Documentación de Amanda IA

Esta carpeta contiene la documentación y herramientas de prueba para la API de Amanda IA.

## 📋 Contenido

### 📖 Documentación
- **`api_examples.md`** - Ejemplos completos de uso de la API con curl
- **`README.md`** - Este archivo

### 🔧 Scripts de Prueba
- **`test_api.sh`** - Script completo de pruebas de la API
- **`quick_test.sh`** - Script de prueba rápida

## 🚀 Uso Rápido

### Ejecutar Pruebas Completas
```bash
./resources/docs/test_api.sh
```

### Ejecutar Prueba Rápida
```bash
./resources/docs/quick_test.sh
```

### Ver Documentación
```bash
cat resources/docs/api_examples.md
```

## 📝 Notas

- Los scripts requieren que el servicio esté corriendo en `http://localhost:8000`
- Se recomienda tener `jq` instalado para mejor formato de salida JSON
- Todos los ejemplos están probados y funcionando

## 🎯 Casos de Uso

1. **Verificar servicio**: GET `/`
2. **Chat básico**: POST `/chat` con mensaje simple
3. **Consultas de fecha**: POST `/chat` preguntando por la fecha
4. **Análisis Wahapedia**: POST `/chat` con URL de Wahapedia

Para más detalles, consulta `api_examples.md`. 