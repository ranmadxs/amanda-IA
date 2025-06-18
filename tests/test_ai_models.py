import unittest
from datetime import datetime
from amanda_ia.services.ai_models import AIAModels
import logging
from aia_utils.logs_cfg import config_logger

# Configurar el logger
config_logger()
logger = logging.getLogger(__name__)

# Inicializar el modelo
ai_models = AIAModels()

def get_system_message():
    """Obtiene el mensaje del sistema con la fecha actual."""
    current_date = datetime.now().strftime("%d de %B de %Y")
    current_date_iso = datetime.now().strftime("%Y/%m/%d")
    current_year = datetime.now().strftime("%Y")
    
    return f"""Eres un asistente útil. La fecha de hoy es {current_date} ({current_date_iso}).

INSTRUCCIONES CRÍTICAS:
1. Cuando te pregunten por la fecha, DEBES responder ÚNICAMENTE con la fecha exacta proporcionada arriba
2. NO agregues saludos, explicaciones ni información adicional
3. NO inventes fechas ni uses formatos diferentes
4. NO menciones ubicaciones ni otra información no relacionada

Ejemplo:
Usuario: "que fecha es hoy?"
Asistente: "{current_date}"

Usuario: "what's today's date?"
Asistente: "{current_date_iso}"

Recuerda: Mantén las respuestas cortas y directas. Usa SOLO la fecha exacta proporcionada.""", current_date, current_date_iso, current_year

def verify_basic_response(response):
    """Verifica las propiedades básicas de una respuesta."""
    assert response is not None, "La respuesta no debe ser None"
    assert isinstance(response, str), "La respuesta debe ser un string"
    assert len(response) > 0, "La respuesta no debe estar vacía"

#poetry run pytest tests/test_ai_models.py::test_simple_message -s
def test_simple_message():
    """Test para un mensaje simple 'hola'."""
    system_message, current_date, current_date_iso, current_year = get_system_message()
    
    # Preparar los mensajes
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": "hola"}
    ]
    
    # Generar respuesta
    response = ai_models.generate_response(messages)
    
    # Verificar la respuesta
    logger.info("Mensaje de prueba: hola")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar propiedades básicas
    verify_basic_response(response)
    
    # Verificar que la respuesta no contenga la fecha (ya que no se preguntó por ella)
    assert current_date not in response, "La respuesta no debe contener la fecha actual"
    assert current_date_iso not in response, "La respuesta no debe contener la fecha ISO actual"

#poetry run pytest tests/test_ai_models.py::test_date_question -s
def test_date_question():
    """Test para verificar la respuesta cuando se pregunta por la fecha."""
    system_message, current_date, current_date_iso, current_year = get_system_message()
    
    # Preparar los mensajes
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": "que fecha es hoy?"}
    ]
    
    # Generar respuesta
    response = ai_models.generate_response(messages)
    
    # Verificar la respuesta
    logger.info("Mensaje de prueba: que fecha es hoy?")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar propiedades básicas
    verify_basic_response(response)
    
    # Verificar que la respuesta contenga el año actual
    assert current_year in response, f"La respuesta debe contener el año actual: {current_year}"

if __name__ == '__main__':
    unittest.main() 