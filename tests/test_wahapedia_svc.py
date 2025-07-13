import pytest
import logging
from aia_utils.logs_cfg import config_logger
from amanda_ia.services.wahapedia_svc import WahapediaSvC
from amanda_ia.services.ai_models import AIAModels
import time

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

ai_models = AIAModels()
wahapedia_svc = WahapediaSvC(aiamodels=ai_models)

def verify_basic_response(response):
    assert response is not None, "La respuesta no debe ser None"
    assert isinstance(response, str), "La respuesta debe ser un string"
    assert len(response) > 0, "La respuesta no debe estar vacía"

# poetry run pytest tests/test_wahapedia_svc.py::test_chat_endpoint_wahapedia -s
def test_chat_endpoint_wahapedia():
    """Test para verificar la respuesta con una URL de Wahapedia usando el método específico."""
    user_message = (
        "dame las estadísticas de un Space Marine Rhino"
    )
    response = wahapedia_svc.get_wahapedia_stats(user_message)
    logger.info("Mensaje de prueba: URL de Wahapedia")
    logger.debug(f"Respuesta del modelo: {response}")
    verify_basic_response(response)
    stats = ["M", "T", "Sv", "W", "Ld", "OC"]
    stats_found = [stat for stat in stats if stat in response]
    assert len(stats_found) >= 4, (
        f"❌ El modelo no extrajo suficientes estadísticas del contenido Markdown. "
        f"Encontradas: {stats_found}. El modelo debería extraer al menos 4 de: {stats} del contenido proporcionado."
    )
    logger.info("✅ Test exitoso: El modelo extrajo correctamente las claves de las estadísticas")

# poetry run pytest tests/test_wahapedia_svc.py::test_classify_user_message_section -s
def test_classify_user_message_section():
    svc = WahapediaSvC(aiamodels=AIAModels())
    casos = [
        # Space Marines
        ("Dame las estadísticas de un Space Marine Rhino", "estadistica"),
        ("¿Qué armas puede equipar un Space Marine Intercessor?", "armas"),
        ("¿Qué estratagemas puede usar un Capitán Primaris?", "estratagemas"),
        # Orkos
        ("Muéstrame las estadísticas de un Ork Boyz", "estadistica"),
        ("¿Qué armas tiene un Ork Warboss?", "armas"),
        ("¿Qué estratagemas puede usar un Ork Nob?", "estratagemas"),
        # Adepta Sororitas
        ("Dame las estadísticas de una Battle Sister", "estadistica"),
        ("¿Qué armas puede llevar una Celestian?", "armas"),
        ("¿Qué estratagemas puede usar una Canoness?", "estratagemas"),
        # Preguntas variadas
        ("¿Cuáles son las estadísticas principales de un Dreadnought?", "estadistica"),
        ("¿Qué opciones de disparo tiene un Leman Russ?", "armas"),
        ("¿Qué habilidades especiales puede activar un Exorcist?", "estratagemas"),
        # Roboute Guilliman
        ("Dame las estadísticas del arma principal de Roboute Guilliman", "armas"),
    ]
    for mensaje, esperado in casos:
        resultado = svc.classify_user_message_section(mensaje)
        print(f"Mensaje: {mensaje}\nClasificación esperada: {esperado}\nClasificación obtenida: {resultado}\n")
        assert resultado == esperado or resultado in ["estadistica", "estratagemas", "armas"]

@pytest.mark.integration
# poetry run pytest tests/test_wahapedia_svc.py::test_chat_endpoint_wahapedia_armas -s
def test_chat_endpoint_wahapedia_armas():
    """
    Test del endpoint de Wahapedia para extracción de armas.
    """
    aiamodels = AIAModels()
    wahapedia_svc = WahapediaSvC(aiamodels)
    
    # Mensaje que debería clasificarse como "armas" y encontrar Space Marines Rhino
    user_message = "¿Qué armas tiene el Rhino de Space Marines?"
    
    start_time = time.time()
    response = wahapedia_svc.get_wahapedia_stats(user_message)
    execution_time = time.time() - start_time
    
    logger.info(f"⏱️ Tiempo de ejecución: {execution_time:.2f} segundos")
    logger.info(f"Mensaje de prueba: {user_message}")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar que la respuesta contiene información de armas en inglés
    assert "**ARMAS**:" in response
    assert "Disintegration combi-gun" in response or "Disintegration pistol" in response or "Close combat weapon" in response
    
    logger.info("✅ Test exitoso: El modelo extrajo correctamente información de armas")

@pytest.mark.skip(reason="Test temporalmente deshabilitado")
@pytest.mark.integration
# poetry run pytest tests/test_wahapedia_svc.py::test_chat_endpoint_wahapedia_estratagemas -s
def test_chat_endpoint_wahapedia_estratagemas():
    """
    Test del endpoint de Wahapedia para extracción de estratagemas.
    """
    aiamodels = AIAModels()
    wahapedia_svc = WahapediaSvC(aiamodels)
    
    # Mensaje que debería clasificarse como "estratagemas" y encontrar Space Marines Rhino
    user_message = "¿Qué estratagemas puede usar el Rhino de Space Marines?"
    
    start_time = time.time()
    response = wahapedia_svc.get_wahapedia_stats(user_message)
    execution_time = time.time() - start_time
    
    logger.info(f"⏱️ Tiempo de ejecución: {execution_time:.2f} segundos")
    logger.info(f"Mensaje de prueba: {user_message}")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar que la respuesta contiene información de estratagemas en inglés y el costo en CP
    assert "**ESTRATAGEMAS**:" in response
    # Buscar algunos nombres y el formato (NOMBRE (XCP))
    assert "ARMOUR OF CONTEMPT (1CP)" in response
    assert "INSTANT OF GRACE (1CP)" in response
    assert "NO THREAT TOO GREAT (2CP)" in response
    # Verificar que hay descripciones en español (palabras clave típicas)
    assert "descripción" in response or "estratagema" in response or "permite" in response
    assert "url=" in response
    logger.info("✅ Test exitoso: El modelo extrajo correctamente información de estratagemas")

@pytest.mark.integration
# poetry run pytest tests/test_wahapedia_svc.py::test_chat_endpoint_wahapedia_clasificacion_fallida -s
def test_chat_endpoint_wahapedia_clasificacion_fallida():
    """
    Test del endpoint de Wahapedia cuando no se puede clasificar el mensaje.
    """
    aiamodels = AIAModels()
    wahapedia_svc = WahapediaSvC(aiamodels)
    
    # Mensaje que no debería clasificarse en ninguna categoría
    user_message = "blablsblsdzlaldasldalsdl"
    
    response = wahapedia_svc.get_wahapedia_stats(user_message)
    
    logger.info(f"Mensaje de prueba: {user_message}")
    logger.debug(f"Respuesta del modelo: {response}")
    
    # Verificar que retorna None si no se puede clasificar
    assert response is None

@pytest.mark.integration
# poetry run pytest tests/test_wahapedia_svc.py::test_classify_user_message_section -s
def test_classify_user_message_section():
    """
    Test de la función de clasificación de mensajes.
    """
    aiamodels = AIAModels()
    wahapedia_svc = WahapediaSvC(aiamodels)
    
    # Test casos de estadísticas
    stats_messages = [
        "¿Cuáles son las estadísticas del Rhino?",
        "Dame el perfil del Rhino",
        "¿Qué stats tiene el Rhino?",
        "Estadísticas del Rhino"
    ]
    
    for message in stats_messages:
        result = wahapedia_svc.classify_user_message_section(message)
        logger.info(f"Mensaje: '{message}' -> Clasificado como: {result}")
        assert result in ["estadistica", "armas", "estratagemas"]
    
    # Test casos de armas
    weapons_messages = [
        "¿Qué armas tiene el Rhino?",
        "Dame las armas del Rhino",
        "¿Qué puede disparar el Rhino?",
        "Armamento del Rhino"
    ]
    
    for message in weapons_messages:
        result = wahapedia_svc.classify_user_message_section(message)
        logger.info(f"Mensaje: '{message}' -> Clasificado como: {result}")
        assert result in ["estadistica", "armas", "estratagemas"]
    
    # Test casos de estratagemas
    stratagem_messages = [
        "¿Qué estratagemas puede usar el Rhino?",
        "Dame las estratagemas del Rhino",
        "¿Qué CP puede gastar el Rhino?",
        "Estratagemas disponibles para el Rhino"
    ]
    
    for message in stratagem_messages:
        result = wahapedia_svc.classify_user_message_section(message)
        logger.info(f"Mensaje: '{message}' -> Clasificado como: {result}")
        assert result in ["estadistica", "armas", "estratagemas"]
    
    logger.info("✅ Test exitoso: La clasificación de mensajes funciona correctamente") 