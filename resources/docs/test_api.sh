#!/bin/bash

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