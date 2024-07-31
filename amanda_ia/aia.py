
from aia_utils.Queue import QueueConsumer, QueueProducer
import os
from aia_utils.logs_cfg import config_logger
import logging
from aia_utils.mqtt import MqttClient

class AIAService:

    def __init__(self, topic_producer, topic_consumer, version):
        self.topic_consumer = topic_consumer
        self.topic_producer = topic_producer
        self.queueProducer = QueueProducer(self.topic_producer, version, "amanda-ia")
        self.version = version
        self.queueDevice = QueueProducer(os.environ['CLOUDKAFKA_TOPIC_DEVICE_PRODUCER'], version, "amanda-ia")
        config_logger()
        self.logger = logging.getLogger(__name__)
        topic = os.environ['MQTT_TOPIC_PRODUCER']
        self.logger.info("Test Produce mqtt " + topic)
        client_id = "aia-utils-test-001"
        self.mqtt_client = MqttClient(topic, client_id)


    def send_mqtt_message(self, message):
        self.mqtt_client.send_message(message)
    
    def execute(self, action: str=None, device: str=None, location: str = None) -> str:
        """
        Una función que me permite ejecutar acciones, como por ejemplo encender, apagar una luz, una bomba, etc.
        
        Args:
            action: La acción a ejecutar, por ejemplo encender, apagar, etc.
            location: El lugar donde se va a ejecutar la acción, por ejemplo "sala", "cocina", etc.
            device: dispositivo a ejecutar la acción, por ejemplo "luz", "bomba", etc.
        """
        self.logger.info(f"execute action {action}.{device} in [{location}]")
        self.send_mqtt_message(f"execute action {action}.{device} in [{location}]")
        return "acabo de ejecutar la acción {action} en >> {location}!"