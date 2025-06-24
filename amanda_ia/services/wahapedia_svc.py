import logging
import os
import json
import uuid
import datetime
from typing import List, Dict, Any
from aia_utils.logs_cfg import config_logger
from .ai_models import AIAModels
from aia_read_svc.repositories.aiaWh40kRepo import AIAWH40KRepository
from aia_read_svc.wh40kSvc import Warhammer40KService
from dotenv import load_dotenv
from aia_utils.toml_utils import getVersion
from amanda_ia.services.html_extractor import HTMLExtractor
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from transformers import pipeline
# Cargar variables de entorno
load_dotenv()

class WahapediaSvC:
    def __init__(self, aiamodels: AIAModels):
        config_logger()
        self.aiaWHRepo = AIAWH40KRepository(os.environ['MONGODB_URI'])
        self.logger = logging.getLogger(__name__)
        self.aiamodels = aiamodels
        self.html_extractor = HTMLExtractor()
        self.wh40Svc = Warhammer40KService(
            os.environ.get('CLOUDKAFKA_TOPIC_PRODUCER'), 
            getVersion(), 
            os.getenv("WH40K_IMG_FILES_PATH"))
        
        # Inicialización del clasificador de secciones
        self.options_classifier = ["estadistica", "estratagemas", "armas"]
        self.model_classifier = SentenceTransformer('Qwen/Qwen3-Embedding-0.6B')
        self.options_embeddings_classifier = self.model_classifier.encode(self.options_classifier)
        
        # Inicialización del pipeline de Question-Answering
        self.logger.info("Inicializando pipeline de Question-Answering...")
        self.qa_pipeline_classifier = pipeline("question-answering", model="deepset/roberta-base-squad2")
        self.logger.info("Pipeline de Question-Answering inicializado.")

    def _save_to_target(self, data_to_save: Dict, filename_prefix: str):
        """
        Guarda un diccionario en un archivo JSON en la carpeta target/wh40k con un nombre de archivo único.
        """
        try:
            target_dir = os.path.join("target", "wh40k")
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            timestamp = datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            random_id = str(uuid.uuid4())[:8]
            filename = f"{timestamp}_{random_id}_{filename_prefix}.json"
            filepath = os.path.join(target_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            
            self.logger.info(f"Datos guardados en: {filepath}")

        except Exception as e:
            self.logger.error(f"Error al guardar archivo JSON: {str(e)}")

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
        Dado un mensaje del usuario, obtiene la URL de Wahapedia y extrae el contenido según la clasificación del mensaje.
        """
        # Clasificar primero
        section_type = self.classify_user_message_section(user_message)
        if not section_type or section_type not in ["estadistica", "estratagemas", "armas"]:
            return None
        wahapedia_url = self.get_url_base_unit(user_message)
        if not wahapedia_url or (isinstance(wahapedia_url, tuple) and (wahapedia_url[0] is None or wahapedia_url[1] is None)):
            return None
        
        try:
            stats_content, weapons_content, stratagems_content = self.html_extractor.get_wahapedia_content(wahapedia_url)
            
            # Clasificar el mensaje del usuario para determinar qué contenido extraer
            section_type = self.classify_user_message_section(user_message)
            self.logger.info(f"Mensaje clasificado como: {section_type}")
            
            if section_type == "estadistica":
                if not stats_content:
                    return f"No se encontró contenido de estadísticas en {wahapedia_url}"
                prompt = f"""
                Extrae las estadísticas del perfil de la siguiente unidad de Warhammer 40k.
                Responde solo con las estadísticas en formato: M: X, T: Y, Sv: Z, W: A, Ld: B, OC: C
                
                Contenido:
                {stats_content}
                """
                system_prompt = (
                    "Eres un experto en Warhammer 40k y tu tarea es extraer únicamente las estadísticas del perfil de una unidad a partir de un texto en markdown. "
                    "Devuelve solo las estadísticas en el formato: M: X, T: Y, Sv: Z, W: A, Ld: B, OC: C. "
                    "No incluyas explicaciones ni texto adicional."
                )
                extracted_content = self.aiamodels.chat(prompt, system_message=system_prompt)
                content_type = "estadísticas"
                self._save_to_target({"prompt": prompt, "context": stats_content, "response": extracted_content}, "stats_extraction")
                
            elif section_type == "armas":
                if not weapons_content:
                    return f"No se encontró contenido de armas en {wahapedia_url}"
                prompt = f"""
                Extrae la información de las armas y equipamiento de la siguiente unidad de Warhammer 40k.
                Devuelve una lista donde el nombre de cada arma esté exactamente como aparece en el texto original en inglés (no lo traduzcas ni modifiques), y la descripción esté en español.
                
                Formato de ejemplo:
                - Disintegration combi-gun: descripción en español
                - Disintegration pistol: descripción en español
                - Close combat weapon: descripción en español
                
                Si el nombre está en inglés, no lo traduzcas bajo ninguna circunstancia.
                
                Contenido:
                {weapons_content}
                """
                system_prompt = (
                    "Eres un experto en Warhammer 40k. Tu tarea es extraer información sobre las armas y equipamiento de una unidad a partir de un texto en markdown. "
                    "Devuelve una lista donde el nombre de cada arma esté exactamente como aparece en el texto original en inglés (no lo traduzcas ni modifiques), y la descripción esté en español. "
                    "Incluye información como tipo de arma, alcance, fuerza, etc., pero solo la descripción debe estar en español. No traduzcas ni modifiques los nombres de las armas."
                )
                extracted_content = self.aiamodels.chat(prompt, system_message=system_prompt)
                content_type = "armas"
                self._save_to_target({"prompt": prompt, "context": weapons_content, "response": extracted_content}, "weapons_extraction")
                
            elif section_type == "estratagemas":
                if not stratagems_content:
                    return f"No se encontró contenido de estratagemas en {wahapedia_url}"
                prompt = f"""
                Extrae la información de las estratagemas disponibles para la siguiente unidad de Warhammer 40k.
                Devuelve una lista donde el nombre de cada estratagema esté exactamente como aparece en el texto original (no lo traduzcas ni modifiques), junto con su costo en CP y una breve descripción en español si es posible.
                
                Formato de ejemplo:
                - ARMOUR OF CONTEMPT (1CP): descripción en español
                - INSTANT OF GRACE (1CP): descripción en español
                - NO THREAT TOO GREAT (2CP): descripción en español
                
                Si el nombre está en inglés, no lo traduzcas bajo ninguna circunstancia. El costo en CP debe estar entre paréntesis después del nombre.
                
                Contenido:
                {stratagems_content}
                """
                system_prompt = (
                    "Eres un experto en Warhammer 40k. Tu tarea es extraer información sobre las estratagemas disponibles para una unidad a partir de un texto en markdown. "
                    "Devuelve una lista donde el nombre de cada estratagema esté exactamente como aparece en el texto original (no lo traduzcas ni modifiques), junto con su costo en CP y una breve descripción en español si es posible. "
                    "El costo en CP debe estar entre paréntesis después del nombre. No traduzcas ni modifiques los nombres de las estratagemas."
                )
                extracted_content = self.aiamodels.chat(prompt, system_message=system_prompt)
                content_type = "estratagemas"
                self._save_to_target({"prompt": prompt, "context": stratagems_content, "response": extracted_content}, "stratagems_extraction")
                
            else:
                # Si no encuentra una sección válida, retornar error
                return f"Error: No se pudo clasificar el tipo de contenido solicitado. Secciones disponibles: estadísticas, armas, estratagemas."
            
            if extracted_content:
                respuesta = f"**{content_type.upper()}**:\n{extracted_content}"
            else:
                respuesta = f"No se encontró contenido claro de {content_type}."

        except Exception as e:
            self.logger.error(f"Error al extraer contenido o procesar Wahapedia: {str(e)}")
            return f"Error al procesar la solicitud para Wahapedia: {str(e)}"
        
        return f"{respuesta}\n\nurl={wahapedia_url}"

    def classify_user_message_section(self, user_message: str) -> str:
        """
        Clasifica el texto del usuario en 'estadistica', 'estratagemas' o 'armas' usando embeddings Qwen3-Embedding-0.6B.
        """
        try:
            # Embedding del mensaje del usuario
            user_embedding = self.model_classifier.encode([user_message])[0]
            # Calcular similitud de coseno
            similarities = cosine_similarity([user_embedding], self.options_embeddings_classifier)[0]
            best_idx = similarities.argmax()
            return self.options_classifier[best_idx]
        except Exception as e:
            self.logger.error(f"Error en classify_user_message_section: {str(e)}")
            return None