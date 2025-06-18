import unittest
import pytest
from amanda_ia.services.html_extractor import HTMLExtractor
import logging
from aia_utils.logs_cfg import config_logger
import requests
from bs4 import BeautifulSoup

# Configurar el logger
config_logger()
logger = logging.getLogger(__name__)

# Inicializar el extractor
html_extractor = HTMLExtractor()

#poetry run pytest tests/test_html_extractor.py::test_html_content -s
def test_html_content():
    """Test para verificar la extracción de contenido de una URL."""
    # URL de prueba
    url = "https://wahapedia.ru/wh40k10ed/factions/space-marines/Lieutenant"
    
    # Obtener el contenido
    content = html_extractor.get_wahapedia_content(url)
    
    # Verificar la respuesta
    logger.info(f"URL de prueba: {url}")
    logger.debug(f"Contenido extraído: {content}")
    
    # Verificar que el contenido no esté vacío
    assert content is not None, "El contenido no debe ser None"
    assert isinstance(content, str), "El contenido debe ser un string"
    assert len(content) > 0, "El contenido no debe estar vacío"
    
    # Parsear el contenido procesado
    soup = BeautifulSoup(content, 'html.parser')
    
    # Verificar que existen los divs requeridos en el contenido procesado
    banner_div = soup.find('div', class_='dsBannerWrap')
    assert banner_div is not None, "No se encontró el div con clase 'dsBannerWrap' en el contenido procesado"
    logger.info("Div 'dsBannerWrap' encontrado correctamente en el contenido procesado")
    
    h2_header = soup.find('div', class_='dsH2Header')
    assert h2_header is not None, "No se encontró el div con clase 'dsH2Header' en el contenido procesado"
    logger.info("Div 'dsH2Header' encontrado correctamente en el contenido procesado")
    
    profile_wrap = soup.find('div', class_='dsProfileWrap')
    assert profile_wrap is not None, "No se encontró el div con clase 'dsProfileWrap' en el contenido procesado"
    logger.info("Div 'dsProfileWrap' encontrado correctamente en el contenido procesado")
    
    # Verificar que los divs contienen información
    assert len(banner_div.get_text().strip()) > 0, "El div 'dsBannerWrap' está vacío en el contenido procesado"
    assert len(h2_header.get_text().strip()) > 0, "El div 'dsH2Header' está vacío en el contenido procesado"
    assert len(profile_wrap.get_text().strip()) > 0, "El div 'dsProfileWrap' está vacío en el contenido procesado"
  