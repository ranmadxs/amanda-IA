#!/bin/bash

echo "🧪 Probando Amanda IA API..."
echo "================================"

# Test 1: Verificar servicio
echo "1. Verificando servicio..."
if curl -s -X GET http://localhost:8000/ | jq . > /dev/null; then
    echo "✅ Servicio funcionando"
else
    echo "❌ Servicio no disponible"
    exit 1
fi

# Test 2: Chat básico
echo -e "\n2. Chat básico..."
response=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "hola"}')
echo "$response" | jq .
content=$(echo "$response" | sed -n 's/.*"response"[ ]*:[ ]*"\([^"]*\)".*/\1/p')
if [ ${#content} -gt 5 ]; then
    echo "✅ Chat básico: respuesta válida"
else
    echo "❌ Chat básico: respuesta insuficiente"
    exit 2
fi

# Test 3: Pregunta de fecha
echo -e "\n3. Pregunta de fecha..."
response=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "que fecha es hoy?"}')
echo "$response" | jq .
content=$(echo "$response" | sed -n 's/.*"response"[ ]*:[ ]*"\([^"]*\)".*/\1/p')
if [ ${#content} -gt 5 ]; then
    echo "✅ Pregunta de fecha: respuesta válida"
else
    echo "❌ Pregunta de fecha: respuesta insuficiente"
    exit 3
fi

# Test 4: Análisis Wahapedia
echo -e "\n4. Análisis Wahapedia..."
response=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "quiero que revises la siguiente url https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka y me digas las estadísticas principales"}')
echo "$response" | jq .
content=$(echo "$response" | sed -n 's/.*"response"[ ]*:[ ]*"\([^"]*\)".*/\1/p')
if [ ${#content} -gt 5 ]; then
    echo "✅ Wahapedia: respuesta válida"
else
    echo "❌ Wahapedia: respuesta insuficiente"
    exit 4
fi

# Test 5: Comando MQTT (cmd)
echo -e "\n5. Comando MQTT (cmd)..."
response=$(curl -s -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "enciende la bomba del invernadero", "type": "cmd"}')
echo "$response" | jq .
content=$(echo "$response" | sed -n 's/.*"response"[ ]*:[ ]*"\([^"]*\)".*/\1/p')
if [ ${#content} -gt 5 ]; then
    echo "✅ Comando MQTT: respuesta válida"
else
    echo "❌ Comando MQTT: respuesta insuficiente"
    exit 5
fi

echo -e "\n✅ Pruebas completadas!" 