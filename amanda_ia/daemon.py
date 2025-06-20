from argparse import ONE_OR_MORE, ArgumentParser
from . import __version__
import os
from dotenv import load_dotenv
from aia_utils.logs_cfg import config_logger
from amanda_ia.aia import AIAService
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import sys
import traceback
from .services.ai_models import AIAModels
from aia_utils.toml_utils import getVersion
from .models import ChatRequest, ChatResponse
from .services.wahapedia_svc import WahapediaSvC
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.staticfiles import StaticFiles

# Configuración del logger
config_logger()
logger = logging.getLogger(__name__)
load_dotenv()

# Inicialización de los servicios
ai_models = AIAModels()
wahapedia_svc = WahapediaSvC(aiamodels=ai_models)

templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), 'templates'))

app = FastAPI(title="Amanda-IA Chat API")

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializar el servicio AIA con Kafka
aia_service = AIAService(
    topic_producer=os.environ.get('CLOUDKAFKA_TOPIC_PRODUCER', 'amanda-ia-producer'),
    topic_consumer=os.environ.get('CLOUDKAFKA_TOPIC_CONSUMER', 'amanda-ia-consumer'),
    version=getVersion()
)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "templates", "static")), name="static")

@app.get("/status")
async def status():
    """Endpoint para verificar que la API está funcionando."""
    return {"message": "Amanda-IA Chat API is running"}

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        logger.debug(f"Received chat request: {request.message} (type={request.type})")
        if request.type == "cmd":
            response = ai_models.get_mqtt_command(request.message)
        elif request.type == "wh40k":
            response = wahapedia_svc.get_wahapedia_stats(request.message)
        else:
            response = ai_models.chat(request.message)
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
        
        # Iniciar el listener de Kafka en un hilo separado
        import threading
        kafka_thread = threading.Thread(target=aia_service.kafkaListener, daemon=True)
        kafka_thread.start()
        logger.info("Kafka listener thread started")
        
        logger.info("Starting FastAPI server...")
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    run()
