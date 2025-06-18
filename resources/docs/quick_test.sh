#!/bin/bash

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

echo "🎯 Prueba rápida completada!" 