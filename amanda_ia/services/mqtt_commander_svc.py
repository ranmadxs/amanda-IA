import logging
import json
import threading
from typing import List, Dict, Any
from aia_utils.logs_cfg import config_logger
from aia_utils.mqtt import MqttProducer
from amanda_ia.aia import AIAService
from .ai_models import AIAModels

class MqttCommanderSvc:
    def __init__(self, aiamodels: AIAModels):
        config_logger()
        self.logger = logging.getLogger(__name__)
        self.aiamodels = aiamodels

    def _send_mqtt_async(self, topic: str, command: str):
        """Envía un comando MQTT de forma asíncrona."""
        try:
            mqtt_client = MqttProducer(topic, "amanda-ia-mqtt-commander-0019")
            mqtt_client.send_message(command)
            self.logger.info(f"Comando MQTT enviado: {command} al topico {topic}")
        except Exception as e:
            self.logger.error(f"Error al enviar comando MQTT: {str(e)}")

    def get_mqtt_command(self, user_message: str, max_length: int = 128) -> str:
        """
        Dado un mensaje de usuario, devuelve SOLO el comando MQTT si es una orden de control.
        Si no es una orden reconocida, responde 'Comando no reconocido'.
        Al final envía el comando MQTT a la cola de forma asíncrona.
        """
        result = None
        # Similitud primero (opcional, puedes quitar si solo quieres el modelo)
        if hasattr(AIAService, 'phrases'):
            phrases = AIAService.phrases
        else:
            phrases = []
        # Ejemplos dinámicos
        ejemplos = ""
        for p in phrases:
            ejemplos += f"Usuario: '{p['text']}'\nRespuesta: {p['command']}\n"
        # Ejemplos negativos
        ejemplos += (
            "Usuario: 'qué hora es?'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'dime la temperatura'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'riego automático'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'enciende la bomba y las luces'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'cómo está el clima?'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'cuál es el estado del invernadero?'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'enciende todo'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'enciende la bomba y la calefacción'\nRespuesta: Comando no reconocido\n"
        )
        prompt = (
            "Eres un controlador de invernadero.\n"
            "INSTRUCCIONES:\n"
            "- Si el usuario da una orden de encender/apagar dispositivos, responde SOLO con el comando MQTT exacto.\n"
            "- Si la orden no corresponde a un comando conocido, responde exactamente con: Comando no reconocido.\n"
            "- No repitas ejemplos ni des explicaciones, responde solo con un único comando.\n"
            "- NO uses comillas en tu respuesta.\n\n"
            "EJEMPLOS:\n"
            f"{ejemplos}"
            f"Usuario: '{user_message}'\nRespuesta:"
        )
        messages = [
            {"role": "system", "content": prompt}
        ]
        respuesta = self.aiamodels._generate_response_internal(messages, max_length=max_length).strip()
        # Limpiar la respuesta de comillas extra
        comando_limpio = respuesta.splitlines()[0].strip() if respuesta else respuesta
        comando_limpio = comando_limpio.strip("'\"")  # Quitar comillas simples y dobles
        # Si es "Comando no reconocido", devolverlo tal cual
        if comando_limpio.lower() == "comando no reconocido":
            return comando_limpio
        
        topic = None
        # Buscar el comando en la lista de phrases
        json_response = None
        for p in phrases:
            if p["command"] == comando_limpio:
                # Devolver el JSON completo pero con el text del mensaje original
                topic = p["topic"]
                json_response = json.dumps({
                    "text": user_message,
                    "command": p["command"],
                    "topic": p["topic"],
                    "protocol": p["protocol"]
                }, ensure_ascii=False)
                break
        
        # Si no se encuentra el comando en la lista, devolver solo el comando
        if json_response is None:
            json_response = comando_limpio
        
        # Enviar el comando MQTT de forma asíncrona en un hilo separado
        if topic:
            # Ejecutar en un hilo separado para no bloquear la respuesta
            thread = threading.Thread(target=self._send_mqtt_async, args=(topic, comando_limpio))
            thread.daemon = True
            thread.start()
        
        return json_response 