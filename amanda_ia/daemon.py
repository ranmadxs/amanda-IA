from argparse import ONE_OR_MORE, ArgumentParser
from . import __version__
import os
from dotenv import load_dotenv
from aia_utils.logs_cfg import config_logger
from amanda_ia.aia import AIAService
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import sys
import requests
from bs4 import BeautifulSoup
import json
import re
import traceback

config_logger()
logger = logging.getLogger(__name__)
#from aia_utils.logs.logs_cfg import config_logger
#import logging
#config_logger()
#logger = logging.getLogger(__name__)
load_dotenv()
from aia_utils.toml_utils import getVersion

# Inicialización global del modelo y tokenizer
logger.info("Inicializando modelo y tokenizer...")
checkpoint = "Qwen/Qwen2-0.5B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(checkpoint)
if tokenizer.pad_token is None:
    logger.debug("Setting pad_token to eos_token")
    tokenizer.pad_token = tokenizer.eos_token

# Configurar el modelo con más tokens y mejor manejo de memoria
model = AutoModelForCausalLM.from_pretrained(
    checkpoint,
    torch_dtype=torch.float32,
    device_map="auto",
    max_position_embeddings=16384,  # Aumentado de 8192 a 16384
    low_cpu_mem_usage=True,
    offload_folder="offload"  # Para manejar mejor la memoria
)

# Mover el modelo a GPU si está disponible
if torch.cuda.is_available():
    logger.info("GPU disponible, moviendo modelo a CUDA")
    model = model.to("cuda")
else:
    logger.info("GPU no disponible, usando CPU")

logger.info("Modelo y tokenizer inicializados correctamente")

app = FastAPI(title="Amanda-IA Chat API")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

def get_url_content(url: str, max_length: int = 32000) -> str:
    """Obtiene el contenido de una URL y lo devuelve como texto."""
    try:
        logger.debug(f"[URL] Iniciando descarga de contenido desde: {url}")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        logger.debug(f"[URL] Respuesta recibida. Status code: {response.status_code}")
        
        # Parsear el HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        logger.debug("[URL] HTML parseado correctamente")
        
        # Eliminar elementos innecesarios
        for element in soup.find_all(['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript', 'meta', 'link']):
            element.decompose()
            
        # Eliminar elementos con clases o IDs comunes de elementos no deseados
        unwanted_classes = ['menu', 'sidebar', 'footer', 'header', 'nav', 'advertisement', 'banner', 'cookie', 'popup', 'modal', 'breadcrumb', 'pagination', 'related', 'share', 'social', 'tags', 'categories']
        unwanted_ids = ['menu', 'sidebar', 'footer', 'header', 'nav', 'advertisement', 'banner', 'cookie', 'popup', 'modal', 'breadcrumb', 'pagination', 'related', 'share', 'social', 'tags', 'categories']
        
        for class_name in unwanted_classes:
            for element in soup.find_all(class_=lambda x: x and class_name in x.lower()):
                element.decompose()
                
        for id_name in unwanted_ids:
            for element in soup.find_all(id=lambda x: x and id_name in x.lower()):
                element.decompose()
        
        # Encontrar el contenido principal
        main_content = None
        
        # Intentar encontrar el contenido principal por etiquetas comunes
        for tag in ['main', 'article', 'section', 'div']:
            main_content = soup.find(tag, class_=lambda x: x and any(word in x.lower() for word in ['content', 'main', 'article', 'post', 'entry']))
            if main_content:
                break
        
        # Si no se encuentra contenido principal, usar el body
        if not main_content:
            main_content = soup.find('body')
        
        if main_content:
            # Extraer texto manteniendo la estructura y los tags
            text_parts = []
            seen_texts = set()  # Para evitar duplicados
            
            # Procesar encabezados
            for header in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                text = str(header)  # Mantener los tags HTML
                if text and text not in seen_texts:
                    text_parts.append(f"\n{text}\n")
                    seen_texts.add(text)
            
            # Procesar párrafos y listas
            for element in main_content.find_all(['p', 'li', 'td', 'th']):
                text = str(element)  # Mantener los tags HTML
                if text and text not in seen_texts:
                    text_parts.append(text)
                    seen_texts.add(text)
            
            # Unir todo el texto
            text = '\n'.join(text_parts)
        else:
            # Fallback: obtener todo el texto con tags
            text = str(main_content)
        
        # Limpiar el texto manteniendo los tags
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        # Eliminar repeticiones de palabras clave comunes
        words = text.split()
        cleaned_words = []
        last_words = []  # Para detectar repeticiones de frases
        
        for word in words:
            # Ignorar palabras muy cortas o números
            if len(word) <= 2 or word.isdigit():
                cleaned_words.append(word)
                continue
                
            # Mantener un historial de las últimas palabras
            last_words.append(word)
            if len(last_words) > 3:  # Mantener solo las últimas 3 palabras
                last_words.pop(0)
            
            # Si la palabra actual forma parte de una frase repetida, saltarla
            if len(last_words) == 3 and all(w in text for w in [' '.join(last_words)] * 2):
                continue
                
            cleaned_words.append(word)
        
        text = ' '.join(cleaned_words)
        
        # Eliminar espacios múltiples y líneas vacías
        text = ' '.join(text.split())
        
        # Truncar el texto si es muy largo
        if len(text) > max_length:
            logger.debug(f"[URL] Contenido truncado de {len(text)} a {max_length} caracteres")
            text = text[:max_length] + "... [contenido truncado]"
        
        logger.debug(f"[URL] Contenido extraído y limpiado. Longitud final: {len(text)} caracteres")
        logger.debug(f"[URL] Primeros 200 caracteres del contenido: {text[:200]}")
        
        return text
    except requests.exceptions.Timeout:
        logger.error(f"[URL] Timeout al intentar acceder a: {url}")
        return f"Error: Timeout al intentar acceder a la URL {url}"
    except requests.exceptions.RequestException as e:
        logger.error(f"[URL] Error al acceder a {url}: {str(e)}")
        return f"Error al acceder a la URL {url}: {str(e)}"
    except Exception as e:
        logger.error(f"[URL] Error inesperado al procesar {url}: {str(e)}")
        return f"Error inesperado al procesar la URL {url}: {str(e)}"

@app.get("/")
async def root():
    return {"message": "Amanda-IA Chat API is running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        logger.debug(f"Received chat request: {request.message}")
        
        # Detectar URLs en el mensaje
        url_pattern = r'https?://\S+'
        urls = re.findall(url_pattern, request.message)
        
        if urls:
            logger.debug(f"URLs detectadas en el mensaje: {urls}")
            # Obtener contenido de todas las URLs
            url_contents = {}
            for url in urls:
                content = get_url_content(url)
                url_contents[url] = content
            
            # Agregar el contenido de las URLs al mensaje del sistema
            system_message = "You are a helpful assistant that can fetch and analyze content from URLs. "
            system_message += "I will provide you with the content of the URLs mentioned in the user's message. "
            system_message += "Please analyze this content and provide a detailed response based on it.\n\n"
            
            for url, content in url_contents.items():
                system_message += f"Content from {url}:\n{content}\n\n"
            
            # Truncar el mensaje del sistema si es muy largo
            max_system_length = 64000  # Aumentado de 15000 a 64000
            if len(system_message) > max_system_length:
                logger.debug(f"Sistema: Mensaje truncado de {len(system_message)} a {max_system_length} caracteres")
                system_message = system_message[:max_system_length] + "... [contenido truncado]"
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": request.message}
            ]
        else:
            messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": request.message}
            ]
        
        # Preparar el prompt
        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )
        
        logger.debug(f"Prompt preparado. Longitud: {len(prompt)} caracteres")
        
        # Tokenizar el prompt
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=8192,
            padding=True
        )
        
        # Mover inputs a GPU si está disponible
        if torch.cuda.is_available():
            inputs = {k: v.to("cuda") for k, v in inputs.items()}
        
        logger.debug("Generating response...")
        outputs = model.generate(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            pad_token_id=tokenizer.pad_token_id,
            max_new_tokens=2048,  # Aumentado de 1024 a 2048
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.2,  # Añadido para evitar repeticiones
            length_penalty=1.0,  # Añadido para controlar la longitud
            no_repeat_ngram_size=3  # Añadido para evitar repeticiones de frases
        )
        
        # Decodificar la respuesta
        response_text = tokenizer.decode(
            outputs[0],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=True,
            spaces_between_special_tokens=False
        )
        
        logger.debug(f"Response text before cleaning: {response_text}")
        
        # Parsear la respuesta por roles
        lines = response_text.strip().split('\n')
        roles_and_messages = []
        current_role = None
        current_message = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.lower() in ['system', 'user', 'assistant']:
                # Si teníamos un rol anterior, guardamos su mensaje
                if current_role and current_message:
                    roles_and_messages.append((current_role, ' '.join(current_message)))
                current_role = line.lower()
                current_message = []
            else:
                current_message.append(line)
        
        # Agregar el último rol y mensaje
        if current_role and current_message:
            roles_and_messages.append((current_role, ' '.join(current_message)))
        
        # Obtener solo la respuesta del asistente
        assistant_response = None
        for role, message in roles_and_messages:
            if role == 'assistant':
                assistant_response = message
                break
        
        if not assistant_response:
            assistant_response = response_text
            
        logger.debug(f"Final assistant response: {assistant_response}")
        return ChatResponse(response=assistant_response)
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

def run():
    """
    entry point
    """
    try:
        logger.info(f"Start Daemon amanda-IA v{getVersion()}")
        logger.info("Starting FastAPI server...")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run()
