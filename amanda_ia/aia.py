from aia_utils.Queue import QueueConsumer, QueueProducer
import os
from aia_utils.logs_cfg import config_logger
import logging
from aia_utils.mqtt import MqttProducer, MqttConsumer
from transformers import AutoModel, AutoTokenizer
import torch
from sklearn.metrics.pairwise import cosine_similarity, euclidean_distances
class AIAService:

    phrases = [
        {
            "text": "enciende las luces para las personas del invernadero.",
            "command": "ON,6,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },
        {
            "text": "enciende la bomba del invernadero.",
            "command": "ON,2,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },
        {
            "text": "enciende los ventiladores del invernadero.",
            "command": "ON,3,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },
        {
            "text": "apaga todo en el invernadero.",
            "command": "OFF,0,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },
        {
            "text": "enciende todo en el invernadero.",
            "command": "ON,0,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },
        {
            "text": "enciende las luces del invernadero.",
            "command": "ON,0,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },      
        {
            "text": "apaga las luces del invernadero.",
            "command": "OFF,0,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        },      
        {
            "text": "enciende las luces de las plantas en el invernadero.",
            "command": "ON,1,0,0,0,0,0,0",
            "topic": "yai-mqtt/in",
            "protocol": "MQTT"
        }
    ]

    def get_embeddings_phrases(self):
        # Lista para almacenar los embeddings
        self.embeddings = []
        # Obtener los embeddings de las frases
        for phrase in self.phrases:
            embedding = self.get_embedding(phrase['text'])
            self.embeddings.append(embedding)
        return self.embeddings

    def similarity(self, text):

        # Verificamos si el atributo 'embeddings' existe
        if not hasattr(self, 'embeddings'):
            self.embeddings = self.get_embeddings_phrases()

        embeddingComparative = self.get_embedding(text)
        
        # Lista para almacenar las similitudes de coseno
        cosine_similarities = []
        # Calcular las similitudes de coseno
        for i in range(0, len(self.embeddings)):
            similarity = cosine_similarity([embeddingComparative], [self.embeddings[i]])[0][0]
            cosine_similarities.append((self.phrases[i], similarity))
        # Ordenar por similitud de coseno de mayor a menor
        cosine_similarities.sort(key=lambda x: x[1], reverse=True)

        self.logger.debug("#### Similitudes de coseno (mejor a peor) ####")
        for phrases, similarity in cosine_similarities:
            self.logger.debug(f"'{phrases['text']}': {similarity}")

        # Obtener la frase con mayor similitud
        best_match = cosine_similarities[0][0]

        # Lista para almacenar las distancias euclidianas
        euclidean_distances_list = []
        
        # Calcular la distancia euclidiana
        for i in range(0, len(self.embeddings)):
            distance = euclidean_distances([embeddingComparative], [self.embeddings[i]])[0][0]
            euclidean_distances_list.append((self.phrases[i]['text'], distance))
        
        # Ordenar por distancia euclidiana de menor a mayor
        euclidean_distances_list.sort(key=lambda x: x[1])
        
        self.logger.debug(f"#### Distancias euclidianas (mejor a peor) ####")
        for text, distance in euclidean_distances_list:
            self.logger.debug(f"'{text}': {distance}")
        # Extraer y retornar los valores solicitados: tópico, mensaje, protocolo, y comando
        result = {
            "topic": best_match["topic"],
            "command": best_match["command"],
            "protocol": best_match["protocol"],
            "message": best_match["text"]
        }

        self.logger.info(f"Mejor coincidencia: {result['message']} con similitud {cosine_similarities[0][1]}")
        self.logger.debug(f"Result: {result}")
        return result

    def __init__(self, topic_producer, topic_consumer, version):
        self.topic_consumer = topic_consumer
        self.topic_producer = topic_producer
        #self.queueProducer = QueueProducer(self.topic_producer, version, "amanda-ia")
        self.version = version
        #self.queueDevice = QueueProducer(os.environ['CLOUDKAFKA_TOPIC_DEVICE_PRODUCER'], version, "amanda-ia")
        config_logger()
        self.logger = logging.getLogger(__name__)
        mqtt_topic_prod = os.environ['MQTT_TOPIC_PRODUCER']
        self.logger.info("mqtt topic producer=" + mqtt_topic_prod)
        client_id = "aia-utils-test-001"
        self.mqtt_client = MqttProducer(mqtt_topic_prod, client_id)
        self.model_name = "bert-base-uncased"


    def startModel(self):
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self.model = AutoModel.from_pretrained(self.model_name)

    def get_embedding(self, text):
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=128)
        with torch.no_grad():
            outputs = self.model(**inputs)
        # Extraer el embedding del token [CLS], que está en la primera posición
        cls_embedding = outputs.last_hidden_state[:, 0, :].squeeze().numpy()
        return cls_embedding



    def kafkaListener(self):
        #queueConsumer = QueueConsumer(os.environ['CLOUDKARAFKA_TOPIC'])
        queueConsumer = QueueConsumer(self.topic_consumer)
        queueConsumer.listen(self.callback)


    def callback(self, message):
        """Callback para manejar mensajes entrantes."""
        try:
            self.logger.info(f"Received message: {message}")
            
            # Tratar message como string directo
            sentence = message
            self.logger.info(f"sentence: {sentence}")
            
            result = self.similarity(sentence)
            #self.execute(sentence)
            #self.queueProducer.send_message(message)
            #self.queueDevice.send_message(message)
            #self.mqtt_client.send_message(message)
            self.send_mqtt_message(result['command'])
            #self.logger.info(f"Message sent to {self.topic_producer}: {message}")
            
        except Exception as e:
            self.logger.error(f"Error in callback: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

    def send_mqtt_message(self, message):
        self.mqtt_client.send_message(message)
    
    #Pasar el metodo de la similitud del coseno aca


    def execute(self, accion: str=None, objeto: str=None, ubicacion: str = None) -> str:
        """
        Una función que me permite ejecutar acciones, sobre una ubicación en un objeto.
        Args:
            accion: ejemplos: prender, encender, apagar, detener, etc.
            ubicacion: ejemplos: invernadero, oficina, cocina, dormitorio, etc.
            objeto: ejemplos: luces, ampolleta, luz, bomba, bomba de agua, etc.
        """
        self.logger.info(f"execute action {accion}.{objeto} in [{ubicacion}]")
        self.send_mqtt_message(f"execute action {accion}.{objeto} in [{ubicacion}]")
        return "acabo de ejecutar la acción {accion} en >> {ubicacion}!"