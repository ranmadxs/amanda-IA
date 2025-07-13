import unittest
from datetime import datetime
import logging
from aia_utils.logs_cfg import config_logger
import pytest
import json
import re

# Configurar el logger
config_logger()
logger = logging.getLogger(__name__)

# poetry run pytest tests/test_ai_models.py::test_simple_message -s
def test_simple_message(ai_models, verify_basic_response):
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
def test_date_question(ai_models, verify_basic_response):
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
