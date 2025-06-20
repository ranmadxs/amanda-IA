import pytest
import logging
from aia_utils.logs_cfg import config_logger
from amanda_ia.services.wahapedia_svc import WahapediaSvC
from amanda_ia.services.ai_models import AIAModels

config_logger()
logger = logging.getLogger(__name__)

# poetry run pytest tests/test_wahapedia_svc.py::test_get_key_unit_from_msg -s
def test_get_key_unit_from_msg():
    # Leer tokens desde el archivo
    with open("resources/wh40k/wh40k_tokens.txt", "r", encoding="utf-8") as f:
        units = [line.strip() for line in f if line.strip()]
    msg = "Me puedes decir las reglas del space marine rhino?"
    aiamodels = AIAModels()
    svc = WahapediaSvC(aiamodels=aiamodels)
    logger.info(f"Pregunta: units={units}, msg='{msg}'")
    result = svc.getKeyUnitFromMsg(units, msg)
    logger.info(f"Resultado: {result}")
    clean_result = result.strip().strip("'\"").lower()
    assert clean_result == "space-marines"

# poetry run pytest tests/test_wahapedia_svc.py::test_get_key_unit_from_msg_gretchin -s
def test_get_key_unit_from_msg_gretchin():
    # Leer tokens desde el archivo
    with open("resources/wh40k/wh40k_tokens.txt", "r", encoding="utf-8") as f:
        units = [line.strip() for line in f if line.strip()]
    msg = "¿Cuántos puntos cuestan los gretchins de los orkos?"
    aiamodels = AIAModels()
    svc = WahapediaSvC(aiamodels=aiamodels)
    logger.info(f"Pregunta: units={units}, msg='{msg}'")
    result = svc.getKeyUnitFromMsg(units, msg)
    logger.info(f"Resultado: {result}")
    clean_result = result.strip().strip("'\"").lower()
    assert clean_result == "orks"

# poetry run pytest tests/test_wahapedia_svc.py::test_get_url_base_unit2 -s
def test_get_url_base_unit2():
    # Usar servicios reales
    aiamodels = AIAModels()
    svc = WahapediaSvC(aiamodels=aiamodels)
    
    # Test con una pregunta sobre Space Marines Rhino
    sentence = "Me puedes decir las reglas del space marine rhino ?"
    result = svc.get_url_base_unit(sentence)
    
    # Verificar que el resultado es una URL válida de Wahapedia
    assert result is not None
    assert isinstance(result, str)
    assert "https://wahapedia.ru/wh40k10ed/factions/" in result
    assert "space-marines" in result.lower()
    logger.info(f"URL generada: {result}")

# poetry run pytest tests/test_wahapedia_svc.py::test_get_url_base_unit -s
def test_get_url_base_unit():
    # Usar servicios reales
    aiamodels = AIAModels()
    svc = WahapediaSvC(aiamodels=aiamodels)
    
    # Test con una pregunta sobre Space Marines Rhino
    sentence = "Me puedes decir las reglas del space marine rhino primaris?"
    result = svc.get_url_base_unit(sentence)
    
    # Verificar que el resultado es una URL válida de Wahapedia
    assert result is not None
    assert isinstance(result, str)
    assert "https://wahapedia.ru/wh40k10ed/factions/" in result
    assert "space-marines" in result.lower()
    logger.info(f"URL generada: {result}")

# poetry run pytest tests/test_wahapedia_svc.py::test_get_url_base_unit_no_faction_found -s
def test_get_url_base_unit_no_faction_found():
    # Usar servicios reales
    aiamodels = AIAModels()
    svc = WahapediaSvC(aiamodels=aiamodels)
    
    # Test con una pregunta que no encuentra facción
    sentence = "¿Cuál es el clima en Marte?"
    result = svc.get_url_base_unit(sentence)
    
    # Verificar que retorna None cuando no encuentra facción
    assert result is None
    logger.info("No se encontró facción para la pregunta sobre el clima en Marte")

# poetry run pytest tests/test_wahapedia_svc.py::test_classify_from_list -s
def test_classify_from_list():
    """Test del nuevo método classify_from_list optimizado."""
    aiamodels = AIAModels()
    
    # Test con opciones simples
    options = ["space-marines", "orks", "aeldari"]
    message = "Me puedes decir las reglas del space marine rhino?"
    
    result = aiamodels.classify_from_list_pipeline(options, message)
    logger.info(f"Resultado classify_from_list: {result}")
    
    # Verificar que el resultado está en la lista de opciones
    assert result is not None
    assert result.strip().lower() in [opt.lower() for opt in options]
    
    # Test con opciones más específicas
    units = ["rhino", "tactical-squad", "terminator-squad"]
    unit_message = "How many points do Terminators cost?"
    
    unit_result = aiamodels.classify_from_list(units, unit_message)
    logger.info(f"Resultado classify_from_list (unidades): {unit_result}")
    
    assert unit_result is not None
    assert unit_result.strip().lower() == "terminator-squad" 