# Amanda IA - Ejemplos de API

## 🚀 Iniciar el Servicio

```bash
# Iniciar el servicio en segundo plano
poetry run python -m amanda_ia.daemon &

# Verificar que está funcionando
curl -X GET http://localhost:8000/
```

## 📋 Ejemplos de Uso

### 1. Verificar Estado del Servicio

```bash
curl -X GET http://localhost:8000/
```

**Respuesta esperada:**
```json
{"message":"Amanda-IA Chat API is running"}
```

### 2. Chat Básico

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hola"}'
```

**Respuesta esperada:**
```json
{"response":"Hola! ¿Cómo puedo ayudarte hoy?"}
```

### 3. Pregunta de Fecha

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "que fecha es hoy?"}'
```

**Respuesta esperada:**
```json
{"response":"Hoy es el 18 de junio de 2025."}
```

### 4. Análisis de Wahapedia - Ghazghkull Thraka

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "quiero que revises la siguiente url https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka y me digas las estadísticas principales"}'
```

**Respuesta esperada:**
```json
{
  "response": "Mis disculpas por la confusión anterior. Aquí están las estadísticas principales:\n\nM: 5\nT: 6\nSv: 2+\nW: 10\nLd: 6+\nOC: 4"
}
```

### 5. Análisis de Wahapedia - Lieutenant

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "analiza esta unidad https://wahapedia.ru/wh40k10ed/factions/space-marines/Lieutenant"}'
```

**Respuesta esperada:**
```json
{
  "response": "Las estadísticas principales en este contenido son:\n\n1. M: 6\"\n2. T: 4\n3. Sv: 3+\n4. W: 4\n5. Ld: 6+\n6. OC: 1"
}
```

## 🔧 Scripts de Prueba

### Script de Prueba Completa

```bash
#!/bin/bash
# resources/test_api.sh

echo "🧪 Probando Amanda IA API..."
echo "================================"

# Test 1: Verificar servicio
echo "1. Verificando servicio..."
curl -s -X GET http://localhost:8000/ | jq .

# Test 2: Chat básico
echo -e "\n2. Chat básico..."
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hola"}' | jq .

# Test 3: Pregunta de fecha
echo -e "\n3. Pregunta de fecha..."
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "que fecha es hoy?"}' | jq .

# Test 4: Análisis Wahapedia
echo -e "\n4. Análisis Wahapedia..."
curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "quiero que revises la siguiente url https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka y me digas las estadísticas principales"}' | jq .

echo -e "\n✅ Pruebas completadas!"
```

### Script de Prueba Rápida

```bash
#!/bin/bash
# resources/quick_test.sh

echo "⚡ Prueba rápida de Amanda IA..."

# Verificar servicio
if curl -s -X GET http://localhost:8000/ > /dev/null; then
    echo "✅ Servicio funcionando"
else
    echo "❌ Servicio no disponible"
    exit 1
fi

# Prueba de chat
response=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hola"}')

if echo "$response" | grep -q "response"; then
    echo "✅ Chat funcionando"
else
    echo "❌ Error en chat"
fi
```

## 📊 Casos de Uso Comunes

### Análisis de Unidades de Wahapedia

```bash
# Space Marines
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "analiza https://wahapedia.ru/wh40k10ed/factions/space-marines/Lieutenant"}'

# Orks
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "analiza https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka"}'

# Necrons
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "analiza https://wahapedia.ru/wh40k10ed/factions/necrons/Overlord"}'
```

### Consultas de Fecha

```bash
# Fecha en español
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "que fecha es hoy?"}'

# Fecha en inglés
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what is today date?"}'
```

## 🛠️ Troubleshooting

### Servicio No Responde

```bash
# Verificar si el puerto está en uso
lsof -i :8000

# Reiniciar el servicio
pkill -f "amanda_ia.daemon"
poetry run python -m amanda_ia.daemon &
```

### Error de Conexión

```bash
# Verificar que el servicio esté corriendo
ps aux | grep amanda_ia

# Verificar logs
tail -f logs/amanda_ia.log
```

## 📝 Notas

- El servicio corre en `http://localhost:8000`
- Todas las peticiones deben usar `Content-Type: application/json`
- Las URLs de Wahapedia se procesan automáticamente
- El modelo extrae estadísticas (M, T, Sv, W, Ld, OC, INVULNERABLE SAVE)
- Las respuestas incluyen la fecha actual cuando se solicita 