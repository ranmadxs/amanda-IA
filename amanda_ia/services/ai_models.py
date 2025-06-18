import os
import torch
import logging
import re
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
    
    def _load_default_model(self):
        """Carga el modelo por defecto."""
        try:
            self.logger.info("Inicializando modelo y tokenizer...")
            # Usar un modelo más pequeño y eficiente
            checkpoint = "Qwen/Qwen2-0.5B-Instruct"  # Modelo actual - más rápido
            # checkpoint = "Qwen/Qwen2-7B-Instruct"  # Modelo más grande - mejor para análisis pero más lento
            
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
                    "INSTRUCCIONES ESPECÍFICAS:\n"
                    "1. Busca las estadísticas en el contenido (M, T, Sv, W, Ld, OC)\n"
                    "2. Preséntalas en una lista simple\n"
                    "3. NO inventes, NO hagas suposiciones\n"
                    "4. Solo usa la información que está en el contenido\n\n"
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
    
    def generate_response(self, prompt_or_messages, max_length: int = 512, model_type: str = 'default') -> str:
        """
        Genera una respuesta usando el modelo especificado.
        
        Args:
            prompt_or_messages: El prompt de entrada (string) o lista de mensajes
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
            
            # Preparar el prompt
            if isinstance(prompt_or_messages, list):
                # Procesar URLs de Wahapedia si están presentes
                processed_messages = self._extract_wahapedia_content(prompt_or_messages)
                
                # Log debug para ver qué mensajes se envían al modelo
                self.logger.debug(f"Mensajes procesados que se envían al modelo: {processed_messages}")
                
                # Si es una lista de mensajes, usar el chat template
                prompt = tokenizer.apply_chat_template(
                    processed_messages,
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                # Si es un string, usarlo directamente
                prompt = str(prompt_or_messages)
            
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
    
    def get_version(self) -> str:
        """Obtiene la versión del módulo."""
        return getVersion() 