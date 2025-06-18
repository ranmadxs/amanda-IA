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
    # Extraer el contenido de la respuesta (asumiendo formato JSON: {"response": "..."})
    content=$(echo "$response" | sed -n 's/.*"response"[ ]*:[ ]*"\([^"]*\)".*/\1/p')
    if [ ${#content} -gt 5 ]; then
        echo "✅ Chat funcionando y respuesta válida: $content"
    else
        echo "❌ Chat respondió pero el contenido es insuficiente: '$content'"
        exit 2
    fi
else
    echo "❌ Error en chat: no se encontró la clave 'response'"
    exit 3
fi

echo "🎯 Prueba rápida completada!" 