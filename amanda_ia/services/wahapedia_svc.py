import logging
import os
from typing import List
from aia_utils.logs_cfg import config_logger
from .ai_models import AIAModels
from aia_read_svc.repositories.aiaWh40kRepo import AIAWH40KRepository
from aia_read_svc.wh40kSvc import Warhammer40KService
from dotenv import load_dotenv
from aia_utils.toml_utils import getVersion
from amanda_ia.services.html_extractor import HTMLExtractor
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
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
        self.init_classifier()

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

    def get_wahapedia_stats(self, user_message: str, max_length: int = 512) -> str:
        """
        Dado un mensaje del usuario, obtiene la URL de Wahapedia usando la lógica implementada y extrae SOLO las estadísticas principales encontradas en el contenido.
        Si no se puede generar una URL válida, responde con un mensaje de error.
        """
        wahapedia_url = self.get_url_base_unit(user_message)
        if not wahapedia_url:
            return "No se pudo generar una URL de Wahapedia para el mensaje."
        try:
            # Usar el extractor de la IA si está disponible, si no, crear uno nuevo
            html_extractor = getattr(self.aiamodels, 'html_extractor', None)
            if html_extractor is None:
                html_extractor = HTMLExtractor()
            stats_content, weapons_content, stratagems_content = html_extractor.get_wahapedia_content(wahapedia_url)
            content = stats_content
        except Exception as e:
            return f"Error al extraer contenido de Wahapedia: {str(e)}"
        prompt = (
            "A continuación tienes contenido en formato Markdown extraído de una página de Wahapedia. "
            "Tu tarea es EXTRAER y PRESENTAR SOLO las estadísticas principales que encuentres en el contenido.\n\n"
            "IMPORTANTE: Responde SOLO con una lista de estadísticas encontradas (M, T, Sv, W, Ld, OC, INVULNERABLE SAVE).\n"
            "NO uses function calling ni formato JSON.\n"
            "NO inventes, NO hagas suposiciones, NO interpretes.\n"
            "Solo usa la información que está en el contenido.\n"
            "Si no encuentras una estadística, NO la inventes.\n"
            f"\nContenido a analizar:\n{content}\n"
            "\nResponde SOLO con la lista de estadísticas encontradas en texto libre."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "dime las estadísticas principales."}
        ]
        respuesta = self.aiamodels._generate_response_internal(messages, max_length=max_length).strip()
        return f"{respuesta} - url: {wahapedia_url}"

    def init_classifier(self):
        """
        Inicializa el modelo y embeddings para clasificación de secciones si no están ya inicializados (singleton).
        """
        if not hasattr(self, 'options_classifier'):
            self.options_classifier = ["estadistica", "estratagemas", "armas"]
        if not hasattr(self, 'model_classifier'):
            self.model_classifier = SentenceTransformer('Qwen/Qwen3-Embedding-0.6B')
        if not hasattr(self, 'options_embeddings_classifier'):
            self.options_embeddings_classifier = self.model_classifier.encode(self.options_classifier)

    def classify_user_message_section(self, user_message: str) -> str:
        """
        Clasifica el texto del usuario en 'estadistica', 'estratagemas' o 'armas' usando embeddings Qwen3-Embedding-0.6B.
        """
        try:
            self.init_classifier()
            # Embedding del mensaje del usuario
            user_embedding = self.model_classifier.encode([user_message])[0]
            # Calcular similitud de coseno
            similarities = cosine_similarity([user_embedding], self.options_embeddings_classifier)[0]
            best_idx = similarities.argmax()
            return self.options_classifier[best_idx]
        except Exception as e:
            self.logger.error(f"Error en classify_user_message_section: {str(e)}")
            return None