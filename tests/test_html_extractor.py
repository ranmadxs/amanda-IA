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
    
    # Verificar que el contenido tiene un largo mínimo (al menos 100 caracteres)
    assert len(content) >= 100, f"El contenido debe tener al menos 100 caracteres, actualmente tiene {len(content)}"
    
    # Verificar que el contenido contiene información útil (al menos un título o estadística)
    # Buscar patrones comunes en el contenido de Wahapedia
    has_title = '#' in content  # Títulos en Markdown
    has_stats = any(stat in content for stat in ['M:', 'T:', 'Sv:', 'W:', 'Ld:', 'OC:'])
    has_description = len(content.split('\n')) > 5  # Múltiples líneas
    
    assert has_title or has_stats or has_description, (
        f"El contenido debe contener información útil (título, estadísticas o descripción). "
        f"Contenido actual: {content[:200]}..."
    )
    
    logger.info(f"✅ Test exitoso: Contenido extraído correctamente ({len(content)} caracteres)")
    logger.info(f"   - Tiene título: {has_title}")
    logger.info(f"   - Tiene estadísticas: {has_stats}")
    logger.info(f"   - Tiene descripción: {has_description}")
  