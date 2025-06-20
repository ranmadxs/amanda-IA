import logging
import os
from typing import List
from aia_utils.logs_cfg import config_logger
from .ai_models import AIAModels
from aia_read_svc.repositories.aiaWh40kRepo import AIAWH40KRepository
from aia_read_svc.wh40kSvc import Warhammer40KService
from dotenv import load_dotenv
from aia_utils.toml_utils import getVersion
# Cargar variables de entorno
load_dotenv()

class WahapediaSvC:
    def __init__(self, aiamodels: AIAModels):
        config_logger()
        self.aiaWHRepo = AIAWH40KRepository(os.environ['MONGODB_URI'])
        self.logger = logging.getLogger(__name__)
        self.aiamodels = aiamodels
        self.wh40Svc = Warhammer40KService(
            os.environ.get('CLOUDKAFKA_TOPIC_PRODUCER'), 
            getVersion(), 
            os.getenv("WH40K_IMG_FILES_PATH"))

    def get_url_base_unit(self, sentence: str, edition: str = "wh40k10ed", tokens_file: str = './resources/wh40k/wh40k_tokens.txt') -> tuple:
        with open(tokens_file, "r", encoding="utf-8") as f:
            units = [line.strip() for line in f if line.strip()]
        self.logger.debug(units)
        faction_token = self.getKeyUnitFromMsg(units, sentence)
        if faction_token:
            faction_token = faction_token.strip()
        self.logger.debug(faction_token)
        if faction_token is None:
            return None, None
        keywordsUnits = self.wh40Svc.getUnitListKeywords(faction_token, edition)
        self.logger.debug(keywordsUnits['tokens_factions'])
        unit_token = self.getKeyUnitFromMsg(keywordsUnits['tokens_factions'], sentence)
        self.logger.info(unit_token)
        if unit_token is None:
            return None
        url = f"https://wahapedia.ru/{edition}/factions/{faction_token}/{unit_token}"
        return url

    def getKeyUnitFromMsg(self, list_units: List[str], msg: str) -> str:
        self.logger.debug("Getting key unit from message")
        respuesta = self.aiamodels.classify_from_list(list_units, msg)
        return respuesta 