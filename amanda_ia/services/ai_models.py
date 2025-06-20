import os
import torch
import logging
import re
import datetime
import json
import asyncio
import threading
from typing import List, Dict, Any
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from aia_utils.toml_utils import getVersion
from aia_utils.logs_cfg import config_logger
from aia_utils.mqtt import MqttProducer
from .html_extractor import HTMLExtractor
from amanda_ia.aia import AIAService

# Configurar modo offline y caché para Hugging Face
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['HF_DATASETS_OFFLINE'] = '1'
os.environ['HF_HOME'] = 'models_cache'
os.environ['HF_DATASETS_CACHE'] = 'models_cache'
os.environ['TRANSFORMERS_CACHE'] = 'models_cache'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
os.environ['HF_HUB_DISABLE_EXPERIMENTAL_WARNING'] = '1'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'

class AIAModels:
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AIAModels, cls).__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            # Configuración del logger
            config_logger()
            self.logger = logging.getLogger(__name__)
            self.logger.info("Inicializando modelos de IA...")
            
            # Inicializar modelos
            self.model = None
            self.tokenizer = None
            
            # Inicializar el extractor HTML
            self.html_extractor = HTMLExtractor()
            
            # Cargar modelos solo si no están ya cargados
            if not self.model:
                self._load_default_model()
            
            self._initialized = True
            self.logger.info("Modelos de IA inicializados correctamente")
    
    def _get_system_message_with_date(self):
        """Obtiene el mensaje del sistema con la fecha actual, pero solo responde con la fecha si la pregunta es explícita sobre la fecha."""
        current_date = datetime.datetime.now().strftime("%d de %B de %Y")
        current_date_iso = datetime.datetime.now().strftime("%Y/%m/%d")

        return f"""Eres un asistente útil. La fecha de hoy es {current_date} ({current_date_iso}).

INSTRUCCIONES CRÍTICAS:
1. Si el usuario pregunta explícitamente por la fecha actual, responde ÚNICAMENTE con la fecha exacta proporcionada arriba.
2. Si el usuario saluda, pregunta otra cosa o hace un comentario general, responde de forma natural y NO incluyas la fecha en la respuesta.
3. NO inventes fechas ni uses formatos diferentes.
4. NO menciones ubicaciones ni otra información no relacionada.

Ejemplo:
Usuario: "que fecha es hoy?"
Asistente: "{current_date}"

Usuario: "what's today's date?"
Asistente: "{current_date_iso}"

Usuario: "hola"
Asistente: "¡Hola! ¿En qué puedo ayudarte?"

Usuario: "buenos días"
Asistente: "¡Buenos días! ¿Cómo puedo ayudarte?"

Usuario: "cuéntame un chiste"
Asistente: "¿Por qué el tomate se puso rojo? Porque vio a la ensalada desnuda."

Recuerda: Solo responde con la fecha si la pregunta es explícita sobre la fecha. Para saludos y otras preguntas, responde de forma natural y útil.""", current_date, current_date_iso
    
    def _create_messages_for_model(self, user_message: str, system_message: str = None) -> List[Dict[str, str]]:
        """Crea la lista de mensajes para el modelo basado en el mensaje del usuario."""
        if system_message is None:
            system_message, _, _ = self._get_system_message_with_date()
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ]
    
    def _load_default_model(self):
        """Carga el modelo por defecto."""
        try:
            self.logger.info("Inicializando modelo y tokenizer...")
            # Modelos probados:
            # - devanshamin/Qwen2-1.5B-Instruct-Function-Calling-v1 (function calling, pero responde siempre en JSON)
            # - Qwen/Qwen2-0.5B-Instruct (mejor para respuestas en texto libre)
            # - Qwen/Qwen2-7B-Instruct  # Modelo más grande - mejor para análisis pero más lento
            # - Qwen/Qwen1.5-0.5B-Chat  # Primer modelo probado
            # checkpoint = "Qwen/Qwen2.5-0.5B-Instruct"
            #checkpoint = "Qwen/Qwen2-1.5B-Instruct"
            checkpoint = "Qwen/Qwen2.5-1.5B-Instruct"
            
            # Inicializar el tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                checkpoint,
                cache_dir="models_cache"  # Directorio de caché específico
            )
            if self.tokenizer.pad_token is None:
                self.logger.debug("Setting pad_token to eos_token")
                self.tokenizer.pad_token = self.tokenizer.eos_token
            
            # Configurar el modelo
            self.logger.info("Configurando modelo...")
            self.model = AutoModelForCausalLM.from_pretrained(
                checkpoint,
                torch_dtype=torch.float32,
                device_map="auto",
                low_cpu_mem_usage=True,
                max_position_embeddings=4096,
                offload_folder="offload",
                cache_dir="models_cache"  # Directorio de caché específico
            )
            
            # Mover el modelo a GPU si está disponible
            if torch.cuda.is_available():
                self.logger.info("GPU disponible, moviendo modelo a CUDA")
                self.model = self.model.to("cuda")
            elif torch.backends.mps.is_available():
                self.logger.info("MPS disponible, moviendo modelo a MPS (Apple Silicon/Intel)")
                self.model = self.model.to("mps")
            else:
                self.logger.info("GPU no disponible, usando CPU")
            
            self.logger.info("Modelo y tokenizer inicializados correctamente")
            
        except Exception as e:
            self.logger.error(f"Error al cargar el modelo por defecto: {str(e)}")
            self.model = None
            self.tokenizer = None
    
    def get_model(self, model_type: str = 'default'):
        """
        Obtiene el modelo especificado.
        
        Args:
            model_type: Tipo de modelo a obtener ('default')
            
        Returns:
            El modelo solicitado o None si no está disponible
        """
        if model_type == 'default':
            return self.model
        else:
            self.logger.warning(f"Tipo de modelo no reconocido: {model_type}")
            return None
    
    def get_tokenizer(self, model_type: str = 'default'):
        """
        Obtiene el tokenizer especificado.
        
        Args:
            model_type: Tipo de modelo a obtener ('default')
            
        Returns:
            El tokenizer solicitado o None si no está disponible
        """
        if model_type == 'default':
            return self.tokenizer
        else:
            self.logger.warning(f"Tipo de modelo no reconocido: {model_type}")
            return None
    
    def chat(self, user_message: str, max_length: int = 512, model_type: str = 'default', system_message: str = None) -> str:
        """
        Método principal para chat que recibe solo un string del usuario.
        Maneja internamente toda la lógica de creación de contexto y procesamiento.
        """
        try:

            # Crear mensajes para el modelo
            messages = self._create_messages_for_model(user_message, system_message=system_message)
            # Log debug para ver qué mensajes se envían al modelo
            self.logger.debug(f"Mensajes procesados que se envían al modelo: {messages}")
            # Generar respuesta usando el método interno
            return self._generate_response_internal(messages, max_length, model_type)
        except Exception as e:
            self.logger.error(f"Error en chat: {str(e)}")
            return "Lo siento, hubo un error al procesar tu mensaje."
    
    def _generate_response_internal(self, messages: List[Dict[str, str]], max_length: int = 512, model_type: str = 'default') -> str:
        """
        Método interno para generar respuesta a partir de mensajes ya procesados.
        
        Args:
            messages: Lista de mensajes ya procesados
            max_length: Longitud máxima de la respuesta
            model_type: Tipo de modelo a usar ('default')
            
        Returns:
            La respuesta generada
        """
        try:
            model = self.get_model(model_type)
            tokenizer = self.get_tokenizer(model_type)
            
            if model is None or tokenizer is None:
                self.logger.error("Modelo o tokenizer no disponible")
                return "Lo siento, hubo un error al generar la respuesta."
            
            # Usar el chat template
            prompt = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True
            )
            
            # Tokenizar el input
            inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=2048)
            
            # Mover a la misma device que el modelo
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            
            # Generar respuesta
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=max_length,
                    temperature=0.7,
                    do_sample=True,
                    pad_token_id=tokenizer.eos_token_id
                )
            
            # Decodificar la respuesta completa
            full_response = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # Extraer solo la última respuesta del assistant
            last_assistant = full_response.rsplit('assistant\n', 1)
            if len(last_assistant) > 1:
                response = last_assistant[1].strip()
            else:
                # Si no se encuentra el separador, intentar remover el prompt
                if full_response.startswith(prompt):
                    response = full_response[len(prompt):].strip()
                else:
                    response = full_response.strip()
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error al generar respuesta: {str(e)}")
            return "Lo siento, hubo un error al generar la respuesta."
    
    def generate_response(self, prompt_or_messages, max_length: int = 512, model_type: str = 'default') -> str:
        """
        Método legacy que mantiene compatibilidad con el código existente.
        Si recibe un string, usa el nuevo método chat().
        Si recibe una lista, usa el método interno.
        
        Args:
            prompt_or_messages: El prompt de entrada (string) o lista de mensajes
            max_length: Longitud máxima de la respuesta
            model_type: Tipo de modelo a usar ('default')
            
        Returns:
            La respuesta generada
        """
        if isinstance(prompt_or_messages, str):
            # Si es un string, usar el nuevo método chat
            return self.chat(prompt_or_messages, max_length, model_type)
        else:
            # Si es una lista, usar el método interno (para compatibilidad)
            return self._generate_response_internal(prompt_or_messages, max_length, model_type)
    
    def classify_from_list_pipeline(self, options: List[str], user_message: str) -> str:
        """
        Método optimizado usando pipeline de text-classification para clasificación.
        Mucho más rápido y eficiente que el método basado en chat.
        
        Args:
            options: Lista de opciones disponibles
            user_message: Mensaje del usuario
            
        Returns:
            El elemento de la lista que mejor representa el mensaje del usuario
        """
        try:
            # Crear etiquetas para el pipeline
            labels = options
            
            # Crear el pipeline de clasificación
            classifier = pipeline(
                "zero-shot-classification",
                model="facebook/bart-large-mnli",
                tokenizer="facebook/bart-large-mnli",
                device=0 if torch.cuda.is_available() else -1
            )
            
            # Usar solo el mensaje del usuario como input
            result = classifier(user_message, candidate_labels=labels)
            
            # Retornar la etiqueta con mayor score
            return result['labels'][0]
            
        except Exception as e:
            self.logger.error(f"Error en classify_from_list_pipeline: {str(e)}")
            return None

    def classify_from_list(self, options: List[str], user_message: str) -> str:
        """
        Clasifica usando embeddings y fallback zero-shot-classification.
        Loguea los 3 mayores puntajes de similitud de coseno.
        Si la diferencia entre el mejor y el segundo mejor puntaje es menor a 0.08, prioriza la opción con el nombre más corto.
        """
        def normalize(text):
            return text.replace('-', ' ').replace('_', ' ').lower().strip()
        try:
            norm_options = [normalize(opt) for opt in options]
            norm_message = normalize(user_message)
            from sklearn.metrics.pairwise import cosine_similarity
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer('all-MiniLM-L6-v2')
            option_embeddings = model.encode(norm_options)
            user_embedding = model.encode([norm_message])[0]
            similarities = cosine_similarity([user_embedding], option_embeddings)[0]
            # Log top 3 puntajes
            top3 = sorted(enumerate(similarities), key=lambda x: x[1], reverse=True)[:3]
            for rank, (idx, score) in enumerate(top3, 1):
                self.logger.info(f"Top {rank}: {options[idx]} -> {score:.4f}")
            best_idx = similarities.argmax()
            best_score = similarities[best_idx]
            # Buscar el segundo mejor puntaje
            sorted_indices = similarities.argsort()[::-1]
            second_idx = sorted_indices[1] if len(sorted_indices) > 1 else best_idx
            second_score = similarities[second_idx]
            # Si el mejor score es menor a 0.3, devolver None (sin fallback)
            if best_score < 0.3:
                self.logger.info(f"Similitud máxima muy baja ({best_score:.2f}), devolviendo None.")
                return None
            # Si la diferencia es menor a 0.08 y hay más de 50 opciones, priorizar el nombre más corto
            if len(options) > 50 and abs(best_score - second_score) < 0.08:
                candidates = [best_idx, second_idx]
                shortest = min(candidates, key=lambda i: len(options[i]))
                self.logger.info(f"Diferencia pequeña entre top 2 ({best_score:.4f} vs {second_score:.4f}) y más de 50 opciones, priorizando el más corto: {options[shortest]}")
                return options[shortest]
            # Ajustar el umbral de aceptación a 0.48
            if best_score >= 0.48:
                return options[best_idx]
            else:
                self.logger.info(f"Similitud baja ({best_score:.2f}), fallback estrategia.")
                return self.classify_from_list_pipeline(options, user_message)
        except Exception as e:
            self.logger.error(f"Error en classify_from_list (embeddings): {str(e)}")
            