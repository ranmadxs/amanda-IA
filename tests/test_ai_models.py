import unittest
from datetime import datetime
from amanda_ia.services.ai_models import AIAModels
import logging
from aia_utils.logs_cfg import config_logger
import pytest
import json
import re

# Configurar el logger
config_logger()
logger = logging.getLogger(__name__)

# Inicializar el modelo
ai_models = AIAModels()

def verify_basic_response(response):
    """Verifica las propiedades básicas de una respuesta."""
    assert response is not None, "La respuesta no debe ser None"
    assert isinstance(response, str), "La respuesta debe ser un string"
    assert len(response) > 0, "La respuesta no debe estar vacía"

# poetry run pytest tests/test_ai_models.py::test_simple_message -s
def test_simple_message():
    """Test para un mensaje simple 'hola'."""
    # Generar respuesta usando el nuevo método chat
    response = ai_models.chat("hola")
    
    # Verificar la respuesta
    logger.info("Mensaje de prueba: hola")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar propiedades básicas
    verify_basic_response(response)
    
    # Verificar que la respuesta no contenga la fecha (ya que no se preguntó por ella)
    current_date = datetime.now().strftime("%d de %B de %Y")
    current_date_iso = datetime.now().strftime("%Y/%m/%d")
    assert current_date not in response, "La respuesta no debe contener la fecha actual"
    assert current_date_iso not in response, "La respuesta no debe contener la fecha ISO actual"

# poetry run pytest tests/test_ai_models.py::test_date_question -s
def test_date_question():
    """Test para verificar la respuesta cuando se pregunta por la fecha."""
    # Generar respuesta usando el nuevo método chat
    response = ai_models.chat("que fecha es hoy?")
    
    # Verificar la respuesta
    logger.info("Mensaje de prueba: que fecha es hoy?")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar propiedades básicas
    verify_basic_response(response)
    
    # Verificar que la respuesta contenga el año actual
    current_year = datetime.now().strftime("%Y")
    assert current_year in response, f"La respuesta debe contener el año actual: {current_year}"

# poetry run pytest tests/test_ai_models.py::test_chat_endpoint_wahapedia -s
def test_chat_endpoint_wahapedia():
    """Test para verificar la respuesta con una URL de Wahapedia usando el método específico."""
    # Mensaje que incluye una URL de Wahapedia
    user_message = (
        "quiero que revises la siguiente url https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka "
        "y me digas las estadísticas principales"
    )
    
    # Generar respuesta usando el método específico para Wahapedia
    response = ai_models.get_wahapedia_stats(user_message)
    
    # Verificar la respuesta
    logger.info("Mensaje de prueba: URL de Wahapedia")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar propiedades básicas
    verify_basic_response(response)
    
    # Verificar que la respuesta contenga las estadísticas principales
    stats = ["M", "T", "Sv", "W", "Ld", "OC"]
    stats_found = []
    for stat in stats:
        # Buscar la clave en cualquier formato (lista, tabla, texto libre)
        if stat in response:
            stats_found.append(stat)
    
    assert len(stats_found) >= 4, (
        f"❌ El modelo no extrajo suficientes estadísticas del contenido Markdown. "
        f"Encontradas: {stats_found}. El modelo debería extraer al menos 4 de: {stats} del contenido proporcionado."
    )
    logger.info("✅ Test exitoso: El modelo extrajo correctamente las claves de las estadísticas")

# poetry run pytest tests/test_ai_models.py::test_get_mqtt_command -s
def test_get_mqtt_command():
    # Orden reconocida
    comando = ai_models.get_mqtt_command("por favor puedes encender la luz del invernadero?")
    print(f"Comando para bomba: {comando}")
    
    # Verificar que devuelve un JSON válido para comandos reconocidos
    try:
        json_data = json.loads(comando)
        assert "text" in json_data
        assert "command" in json_data
        assert "topic" in json_data
        assert "protocol" in json_data
        assert "text" in json_data
        # Validar que el comando sigue el patrón MQTT: ON/OFF seguido de números separados por comas
        assert re.match(r'^(ON|OFF),\d+(,\d+)*$', json_data["command"]), f"El comando '{json_data['command']}' no sigue el patrón MQTT esperado"
    except json.JSONDecodeError:
        # Si no es JSON, debe ser "Comando no reconocido" o un comando directo
        assert comando == "Comando no reconocido" or re.match(r'^(ON|OFF),\d+(,\d+)*$', comando)
    
    # Orden no reconocida
    comando2 = ai_models.get_mqtt_command("qué hora es?")
    print(f"Comando para pregunta irrelevante: {comando2}")
    assert "comando no reconocido" in comando2.lower()

if __name__ == '__main__':
    unittest.main() 