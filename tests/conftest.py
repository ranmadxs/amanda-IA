import pytest
import logging
from aia_utils.logs_cfg import config_logger
from amanda_ia.services.ai_models import AIAModels
from amanda_ia.services.wahapedia_svc import WahapediaSvC
from amanda_ia.services.mqtt_commander_svc import MqttCommanderSvc

# Configurar el logger
config_logger()
logger = logging.getLogger(__name__)

@pytest.fixture(scope="session")
def ai_models():
    """
    Fixture de sesión para AIAModels que se inicializa una sola vez para toda la sesión de tests.
    Esto optimiza significativamente el tiempo de ejecución de los tests.
    """
    logger.info("🚀 Inicializando AIAModels singleton para toda la sesión de tests...")
    models = AIAModels()
    logger.info("✅ AIAModels inicializado correctamente")
    return models

@pytest.fixture(scope="session")
def wahapedia_svc(ai_models):
    """
    Fixture de sesión para WahapediaSvC que usa el AIAModels singleton.
    """
    logger.info("🚀 Inicializando WahapediaSvC singleton...")
    svc = WahapediaSvC(aiamodels=ai_models)
    logger.info("✅ WahapediaSvC inicializado correctamente")
    return svc

@pytest.fixture(scope="session")
def mqtt_commander_svc(ai_models):
    """
    Fixture de sesión para MqttCommanderSvc que usa el AIAModels singleton.
    """
    logger.info("🚀 Inicializando MqttCommanderSvc singleton...")
    svc = MqttCommanderSvc(aiamodels=ai_models)
    logger.info("✅ MqttCommanderSvc inicializado correctamente")
    return svc

@pytest.fixture
def verify_basic_response():
    """
    Fixture para verificar las propiedades básicas de una respuesta.
    """
    def _verify(response):
        assert response is not None, "La respuesta no debe ser None"
        assert isinstance(response, str), "La respuesta debe ser un string"
        assert len(response) > 0, "La respuesta no debe estar vacía"
    return _verify 