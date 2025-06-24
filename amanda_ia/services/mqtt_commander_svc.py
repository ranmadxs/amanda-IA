import logging
import json
import threading
from typing import List, Dict, Any
from aia_utils.logs_cfg import config_logger
from aia_utils.mqtt import MqttProducer
from amanda_ia.aia import AIAService
from .ai_models import AIAModels
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

class MqttCommanderSvc:
    def __init__(self, aiamodels: AIAModels):
        config_logger()
        self.logger = logging.getLogger(__name__)
        self.aiamodels = aiamodels
        self.init_classifier()

    def init_classifier(self):
        """
        Inicializa el modelo y embeddings para clasificación de comandos si no están ya inicializados (singleton).
        """
        if not hasattr(self, 'phrases_classifier'):
            if hasattr(AIAService, 'phrases') and AIAService.phrases:
                self.phrases_classifier = AIAService.phrases
            else:
                self.phrases_classifier = []
                self.logger.warning("No se encontraron frases en AIAService.phrases. El clasificador de comandos no funcionará.")

        if not hasattr(self, 'model_classifier'):
            self.model_classifier = SentenceTransformer('Qwen/Qwen3-Embedding-0.6B')

        if not hasattr(self, 'options_embeddings_classifier') and self.phrases_classifier:
            options_text = [p['text'] for p in self.phrases_classifier]
            self.options_embeddings_classifier = self.model_classifier.encode(options_text)

    def _send_mqtt_async(self, topic: str, command: str):
        """Envía un comando MQTT de forma asíncrona."""
        try:
            mqtt_client = MqttProducer(topic, "amanda-ia-mqtt-commander-0019")
            mqtt_client.send_message(command)
            self.logger.info(f"Comando MQTT enviado: {command} al topico {topic}")
        except Exception as e:
            self.logger.error(f"Error al enviar comando MQTT: {str(e)}")

    def get_mqtt_command(self, user_message: str) -> str:
        """
        Dado un mensaje de usuario, devuelve el comando MQTT correspondiente usando un clasificador de embeddings.
        Si no es una orden reconocida, responde 'Comando no reconocido'.
        Al final envía el comando MQTT a la cola de forma asíncrona.
        """
        if not self.phrases_classifier:
            return "Comando no reconocido"
        try:
            # Embedding del mensaje del usuario
            user_embedding = self.model_classifier.encode([user_message])[0]
            # Calcular similitud de coseno
            similarities = cosine_similarity([user_embedding], self.options_embeddings_classifier)[0]
            best_idx = similarities.argmax()
            best_score = similarities[best_idx]
            
            # Umbral de aceptación
            if best_score < 0.5:
                 self.logger.info(f"Similitud de comando baja ({best_score:.2f}), respondiendo 'Comando no reconocido'. Mejor opción: {self.phrases_classifier[best_idx]['text']}")
                 return "Comando no reconocido"
            
            best_phrase = self.phrases_classifier[best_idx]
            comando_limpio = best_phrase['command']
            topic = best_phrase['topic']
            json_response = json.dumps({
                "text": user_message,
                "command": best_phrase["command"],
                "topic": best_phrase["topic"],
                "protocol": best_phrase["protocol"]
            }, ensure_ascii=False)
            if topic:
                thread = threading.Thread(target=self._send_mqtt_async, args=(topic, comando_limpio))
                thread.daemon = True
                thread.start()
            
            return json_response
        except Exception as e:
            self.logger.error(f"Error en get_mqtt_command (clasificador): {str(e)}")
            return "Comando no reconocido" 