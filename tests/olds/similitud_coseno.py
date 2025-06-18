import torch
from transformers import AutoModel, AutoTokenizer
from aia_utils.logs_cfg import config_logger
import logging
config_logger()
logger = logging.getLogger(__name__)

# se puede borrar la cache: /Users/edgsanchez/.cache/huggingface/hub/

# Cargar el modelo y el tokenizador
model_name = "gpt2"  # Puedes cambiar el modelo por otro preentrenado
model_name = "dccuchile/bert-base-spanish-wwm-cased"
model_name = "bert-base-multilingual-cased"
model_name = "bert-base-uncased"


#model_name = "Qwen/Qwen2-0.5B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModel.from_pretrained(model_name)

def get_embedding(text):
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=128)
    with torch.no_grad():
        outputs = model(**inputs)
    # Extraer el embedding del token [CLS], que está en la primera posición
    cls_embedding = outputs.last_hidden_state[:, 0, :]
    return cls_embedding

# Función para calcular la similitud de coseno usando PyTorch
def cosine_similarity_torch(embedding1, embedding2):
    # Asegurar que los tensores sean bidimensionales
    if len(embedding1.shape) == 1:
        embedding1 = embedding1.unsqueeze(0)
    if len(embedding2.shape) == 1:
        embedding2 = embedding2.unsqueeze(0)
    return torch.nn.functional.cosine_similarity(embedding1, embedding2).item()

# Función para calcular la distancia euclidiana usando PyTorch
def euclidean_distance_torch(embedding1, embedding2):
    # Asegurar que los tensores sean bidimensionales
    if len(embedding1.shape) == 1:
        embedding1 = embedding1.unsqueeze(0)
    if len(embedding2.shape) == 1:
        embedding2 = embedding2.unsqueeze(0)
    return torch.dist(embedding1, embedding2).item()

# poetry run pytest tests/similitud_coseno.py::test_cosin -s
def test_cosin():

    texto = "enciende todo en el invernadero."
    embeddingComparative = get_embedding(texto)

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
    
    # Lista para almacenar los embeddings
    embeddings = []

    # Obtener los embeddings de las frases
    for phrase in phrases:
        embedding = get_embedding(phrase['text'])
        embeddings.append(embedding)

    # Lista para almacenar las similitudes de coseno
    cosine_similarities = []
    
    # Calcular las similitudes de coseno
    for i in range(0, len(embeddings)):
        similarity = cosine_similarity_torch(embeddingComparative, embeddings[i])
        cosine_similarities.append((phrases[i]['text'], similarity))
    
    # Ordenar por similitud de coseno de mayor a menor
    cosine_similarities.sort(key=lambda x: x[1], reverse=True)
    print(f"<< '{texto}'")
    print("#### Similitudes de coseno (mejor a peor) ####")
    for text, similarity in cosine_similarities:
        print(f"'{text}': {similarity}")

    # Lista para almacenar las distancias euclidianas
    euclidean_distances_list = []
    
    # Calcular la distancia euclidiana
    for i in range(0, len(embeddings)):
        distance = euclidean_distance_torch(embeddingComparative, embeddings[i])
        euclidean_distances_list.append((phrases[i]['text'], distance))
    
    # Ordenar por distancia euclidiana de menor a mayor
    euclidean_distances_list.sort(key=lambda x: x[1])
    
    print(f"#### Distancias euclidianas (mejor a peor) ####")
    for text, distance in euclidean_distances_list:
        print(f"'{text}': {distance}")
