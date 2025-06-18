from argparse import ONE_OR_MORE, ArgumentParser
from . import __version__
import os
from dotenv import load_dotenv
from aia_utils.logs_cfg import config_logger
from amanda_ia.aia import AIAService
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
import datetime
from .services.ai_models import AIAModels
from .services.html_extractor import HTMLExtractor
from aia_utils.toml_utils import getVersion
from .models import ChatRequest, ChatResponse

# Configuración del logger
config_logger()
logger = logging.getLogger(__name__)
load_dotenv()

# Inicialización de los servicios
ai_models = AIAModels()
html_extractor = HTMLExtractor()

app = FastAPI(title="Amanda-IA Chat API")

@app.get("/")
async def root():
    """Endpoint raíz para verificar que la API está funcionando."""
    return {"message": "Amanda-IA Chat API is running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        logger.debug(f"Received chat request: {request.message}")
        
        # Obtener la fecha actual
        current_date = datetime.datetime.now().strftime("%d de %B de %Y")
        current_date_iso = datetime.datetime.now().strftime("%Y/%m/%d")
        
        # Detectar URLs en el mensaje
        url_pattern = r'https?://\S+'
        urls = re.findall(url_pattern, request.message)
        
        if urls:
            logger.debug(f"URLs detectadas en el mensaje: {urls}")
            # Obtener contenido de todas las URLs
            url_contents = {}
            for url in urls:
                content = html_extractor.get_wahapedia_content(url)
                url_contents[url] = content
            
            # Agregar el contenido de las URLs al mensaje del sistema
            system_message = "You are a helpful assistant that can fetch and analyze content from URLs. "
            system_message += "I will provide you with the content of the URLs mentioned in the user's message. "
            system_message += "Please analyze this content and provide a detailed response based on it.\n\n"
            
            for url, content in url_contents.items():
                system_message += f"Content from {url}:\n{content}\n\n"
            
            # Truncar el mensaje del sistema si es muy largo
            max_system_length = 32000  # Reducido para mejor rendimiento
            if len(system_message) > max_system_length:
                logger.debug(f"Sistema: Mensaje truncado de {len(system_message)} a {max_system_length} caracteres")
                system_message = system_message[:max_system_length] + "... [contenido truncado]"
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": request.message}
            ]
        else:
            system_message = f"""Eres un asistente útil. La fecha de hoy es {current_date} ({current_date_iso}).

INSTRUCCIONES CRÍTICAS:
1. Cuando te pregunten por la fecha, DEBES responder ÚNICAMENTE con la fecha exacta proporcionada arriba
2. NO agregues saludos, explicaciones ni información adicional
3. NO inventes fechas ni uses formatos diferentes
4. NO menciones ubicaciones ni otra información no relacionada

Ejemplo:
Usuario: "que fecha es hoy?"
Asistente: "{current_date}"

Usuario: "what's today's date?"
Asistente: "{current_date_iso}"

Recuerda: Mantén las respuestas cortas y directas. Usa SOLO la fecha exacta proporcionada."""
            
            messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": request.message}
            ]
        
        # Generar respuesta usando el servicio de modelos
        response = ai_models.generate_response(messages)
        
        logger.debug(f"Final assistant response: {response}")
        return ChatResponse(response=response)
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
