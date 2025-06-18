import os
import torch
import logging
import re
import datetime
from typing import List, Dict, Any
from transformers import AutoModelForCausalLM, AutoTokenizer
from aia_utils.toml_utils import getVersion
from aia_utils.logs_cfg import config_logger
from .html_extractor import HTMLExtractor

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
    
    def _detect_and_extract_urls(self, user_message: str) -> Dict[str, str]:
        """Detecta URLs en el mensaje y extrae su contenido."""
        url_pattern = r'https?://\S+'
        urls = re.findall(url_pattern, user_message)
        
        if not urls:
            return {}
        
        self.logger.debug(f"URLs detectadas en el mensaje: {urls}")
        url_contents = {}
        
        for url in urls:
            try:
                content = self.html_extractor.get_wahapedia_content(url)
                url_contents[url] = content
            except Exception as e:
                self.logger.error(f"Error al extraer contenido de {url}: {str(e)}")
                url_contents[url] = f"Error al extraer contenido: {str(e)}"
        
        return url_contents
    
    def _create_system_message_with_urls(self, url_contents: Dict[str, str]) -> str:
        """Crea el mensaje del sistema con contenido de URLs."""
        system_message = "You are a helpful assistant that can fetch and analyze content from URLs. "
        system_message += "I will provide you with the content of the URLs mentioned in the user's message. "
        system_message += "Please analyze this content and provide a detailed response based on it.\n\n"
        
        for url, content in url_contents.items():
            system_message += f"Content from {url}:\n{content}\n\n"
        
        # Truncar el mensaje del sistema si es muy largo
        max_system_length = 32000
        if len(system_message) > max_system_length:
            self.logger.debug(f"Sistema: Mensaje truncado de {len(system_message)} a {max_system_length} caracteres")
            system_message = system_message[:max_system_length] + "... [contenido truncado]"
        
        return system_message
    
    def _create_messages_for_model(self, user_message: str) -> List[Dict[str, str]]:
        """Crea la lista de mensajes para el modelo basado en el mensaje del usuario."""
        # Detectar y extraer contenido de URLs
        url_contents = self._detect_and_extract_urls(user_message)
        
        if url_contents:
            # Si hay URLs, crear mensaje del sistema con contenido de URLs
            system_message = self._create_system_message_with_urls(url_contents)
        else:
            # Si no hay URLs, usar mensaje del sistema con fecha
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
    
    def _extract_wahapedia_content(self, messages):
        """Extrae contenido de URLs de Wahapedia si están presentes en los mensajes."""
        try:
            # Buscar URLs en todos los mensajes
            url_pattern = r'https?://wahapedia\.ru/\S+'
            wahapedia_urls = []
            
            for message in messages:
                if isinstance(message, dict) and 'content' in message:
                    urls = re.findall(url_pattern, message['content'])
                    wahapedia_urls.extend(urls)
            
            if wahapedia_urls:
                self.logger.info(f"URLs de Wahapedia detectadas: {wahapedia_urls}")
                
                # Obtener contenido de todas las URLs
                wahapedia_content = {}
                for url in wahapedia_urls:
                    try:
                        content = self.html_extractor.get_wahapedia_content(url)
                        wahapedia_content[url] = content
                        self.logger.debug(f"Contenido extraído de {url}: {len(content)} caracteres")
                    except Exception as e:
                        self.logger.error(f"Error al extraer contenido de {url}: {str(e)}")
                        wahapedia_content[url] = f"Error al extraer contenido: {str(e)}"
                
                # Crear un mensaje del sistema con el contenido extraído
                system_content = (
                    "Eres un asistente útil. A continuación tienes contenido en formato Markdown extraído de una página de Wahapedia. "
                    "Tu tarea es EXTRAER y PRESENTAR las estadísticas que encuentres en el contenido.\n\n"
                    "IMPORTANTE: Responde SOLO con texto libre. NO uses function calling ni formato JSON.\n\n"
                    "INSTRUCCIONES ESPECÍFICAS:\n"
                    "1. Busca las estadísticas en el contenido (M, T, Sv, W, Ld, OC, INVULNERABLE SAVE)\n"
                    "2. Preséntalas en una lista simple con el formato exacto que aparecen\n"
                    "3. NO inventes, NO hagas suposiciones, NO interpretes\n"
                    "4. Solo usa la información que está en el contenido\n"
                    "5. Si no encuentras una estadística, NO la inventes\n"
                    "6. Responde SOLO con la lista de estadísticas encontradas en texto libre\n\n"
                    "Contenido a analizar:\n"
                )
                for content in wahapedia_content.values():
                    system_content += f"{content}\n\n"
                
                # Truncar si es muy largo
                max_length = 32000
                if len(system_content) > max_length:
                    self.logger.debug(f"Contenido truncado de {len(system_content)} a {max_length} caracteres")
                    system_content = system_content[:max_length] + "... [contenido truncado]"
                
                # Crear nuevos mensajes con el contenido extraído
                new_messages = [
                    {"role": "system", "content": system_content}
                ]
                
                # Agregar el mensaje del usuario original
                if messages and len(messages) > 0:
                    new_messages.append(messages[-1])  # Agregar el último mensaje (usuario)
                
                # Si se detectaron URLs de Wahapedia, modificar el mensaje del usuario
                if wahapedia_urls:
                    # Modificar el último mensaje del usuario para que no incluya la URL
                    for message in messages:
                        if message["role"] == "user":
                            # Reemplazar cualquier referencia a URL con una petición de revisar el contenido
                            original_content = message["content"]
                            # Buscar y reemplazar patrones comunes de URLs de Wahapedia
                            # Eliminar URLs de Wahapedia del mensaje
                            cleaned_content = re.sub(r'https://wahapedia\.ru/[^\s]+', '', original_content)
                            # Limpiar espacios extra y agregar petición clara
                            cleaned_content = cleaned_content.strip()
                            # Simplificar el mensaje para que sea más directo
                            message["content"] = "dime las estadísticas principales."
                            break
                
                return new_messages
            
            return messages
            
        except Exception as e:
            self.logger.error(f"Error al procesar URLs de Wahapedia: {str(e)}")
            return messages
    
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
    
    def chat(self, user_message: str, max_length: int = 512, model_type: str = 'default') -> str:
        """
        Método principal para chat que recibe solo un string del usuario.
        Maneja internamente toda la lógica de creación de contexto y procesamiento.
        """
        try:
            # Crear mensajes para el modelo
            messages = self._create_messages_for_model(user_message)
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
    
    def get_version(self) -> str:
        """Obtiene la versión del módulo."""
        return getVersion()

    def get_mqtt_command(self, user_message: str, max_length: int = 128) -> str:
        """
        Dado un mensaje de usuario, devuelve SOLO el comando MQTT si es una orden de control.
        Si no es una orden reconocida, responde 'Comando no reconocido'.
        """
        prompt = (
            "Eres un controlador de invernadero.\n"
            "INSTRUCCIONES:\n"
            "- Si el usuario da una orden de encender/apagar la bomba, responde SOLO con el comando MQTT exacto para la bomba (ejemplo: ON,2,0,0,0,0,0,0 para encender la bomba, OFF,2,0,0,0,0,0,0 para apagarla).\n"
            "- Si la orden es para las luces, responde SOLO con el comando MQTT exacto para las luces (ejemplo: ON,0,0,0,0,0,0,0 para encender todas las luces).\n"
            "- Si la orden no corresponde a un comando conocido, responde exactamente con: Comando no reconocido.\n"
            "- No repitas ejemplos ni des explicaciones, responde solo con el comando.\n\n"
            "EJEMPLOS:\n"
            "Usuario: 'enciende la bomba del invernadero'\nRespuesta: ON,2,0,0,0,0,0,0\n"
            "Usuario: 'apaga la bomba del invernadero'\nRespuesta: OFF,2,0,0,0,0,0,0\n"
            "Usuario: 'enciende la bomba principal'\nRespuesta: ON,2,0,0,0,0,0,0\n"
            "Usuario: 'apaga la bomba principal'\nRespuesta: OFF,2,0,0,0,0,0,0\n"
            "Usuario: 'enciende la bomba de riego'\nRespuesta: ON,2,0,0,0,0,0,0\n"
            "Usuario: 'apaga la bomba de riego'\nRespuesta: OFF,2,0,0,0,0,0,0\n"
            "Usuario: 'enciende la bomba'\nRespuesta: ON,2,0,0,0,0,0,0\n"
            "Usuario: 'apaga la bomba'\nRespuesta: OFF,2,0,0,0,0,0,0\n"
            "Usuario: 'enciende las luces del invernadero'\nRespuesta: ON,0,0,0,0,0,0,0\n"
            "Usuario: 'apaga las luces del invernadero'\nRespuesta: OFF,0,0,0,0,0,0,0\n"
            "Usuario: 'enciende la luz de las plantas'\nRespuesta: ON,1,0,0,0,0,0,0\n"
            "Usuario: 'enciende la luz principal'\nRespuesta: ON,0,0,0,0,0,0,0\n"
            "Usuario: 'enciende la calefacción del invernadero'\nRespuesta: ON,3,0,0,0,0,0,0\n"
            "Usuario: 'apaga la calefacción del invernadero'\nRespuesta: OFF,3,0,0,0,0,0,0\n"
            "Usuario: 'enciende el ventilador'\nRespuesta: ON,4,0,0,0,0,0,0\n"
            "Usuario: 'apaga el ventilador'\nRespuesta: OFF,4,0,0,0,0,0,0\n"
            # Ejemplos negativos variados al final
            "Usuario: 'qué hora es?'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'dime la temperatura'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'riego automático'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'enciende la bomba y las luces'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'cómo está el clima?'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'cuál es el estado del invernadero?'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'analiza https://wahapedia.ru/wh40k10ed/factions/orks/Ghazghkull-Thraka'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'enciende todo'\nRespuesta: Comando no reconocido\n"
            "Usuario: 'enciende la bomba y la calefacción'\nRespuesta: Comando no reconocido\n"
            f"Usuario: '{user_message}'\nRespuesta:"
        )
        # Generar la respuesta usando directamente el método interno, evitando lógica de URLs
        messages = [
            {"role": "system", "content": prompt}
        ]
        respuesta = self._generate_response_internal(messages, max_length=max_length).strip()
        # Devolver solo la primera línea (el comando MQTT o 'Comando no reconocido')
        return respuesta.splitlines()[0].strip() if respuesta else respuesta 

    def get_wahapedia_stats(self, user_message: str, max_length: int = 512) -> str:
        """
        Dado un mensaje del usuario con una URL de Wahapedia, extrae y devuelve SOLO las estadísticas principales encontradas en el contenido.
        Si no se detecta una URL válida, responde con un mensaje de error.
        """
        # Detectar URL de Wahapedia
        import re
        url_pattern = r'https?://wahapedia\.ru/\S+'
        urls = re.findall(url_pattern, user_message)
        if not urls:
            return "No se detectó una URL de Wahapedia en el mensaje."
        # Extraer contenido de la primera URL encontrada
        wahapedia_url = urls[0]
        try:
            content = self.html_extractor.get_wahapedia_content(wahapedia_url)
        except Exception as e:
            return f"Error al extraer contenido de Wahapedia: {str(e)}"
        # Crear prompt específico para extraer solo las estadísticas
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
        respuesta = self._generate_response_internal(messages, max_length=max_length).strip()
        return respuesta 