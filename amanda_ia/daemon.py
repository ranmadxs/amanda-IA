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

config_logger()
logger = logging.getLogger(__name__)
#from aia_utils.logs.logs_cfg import config_logger
#import logging
#config_logger()
#logger = logging.getLogger(__name__)
load_dotenv()
from aia_utils.toml_utils import getVersion

app = FastAPI(title="Amanda-IA Chat API")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.get("/")
async def root():
    return {"message": "Amanda-IA Chat API is running"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        logger.debug(f"Received chat request: {request.message}")
        
        # Inicializar el modelo y tokenizer
        logger.debug("Loading model and tokenizer...")
        checkpoint = "Qwen/Qwen2-0.5B-Instruct"  # Modelo más ligero y rápido
        tokenizer = AutoTokenizer.from_pretrained(checkpoint)
        
        # Configurar el pad_token si no existe
        if tokenizer.pad_token is None:
            logger.debug("Setting pad_token to eos_token")
            tokenizer.pad_token = tokenizer.eos_token
            
        model = AutoModelForCausalLM.from_pretrained(
            checkpoint,
            torch_dtype=torch.float32,  # Usar float32 para CPU
            device_map="auto"
        )
        logger.debug("Model and tokenizer loaded successfully")

        # Preparar el mensaje
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": request.message}
        ]
        logger.debug(f"Prepared messages: {messages}")

        # Generar respuesta
        logger.debug("Applying chat template...")
        inputs = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt"
        )
        logger.debug(f"Chat template applied. Input shape: {inputs.shape}")
        
        # Crear attention mask
        attention_mask = torch.ones_like(inputs)
        logger.debug(f"Created attention mask with shape: {attention_mask.shape}")
        
        # Mover el tensor al dispositivo correcto
        logger.debug(f"Moving inputs to device: {model.device}")
        inputs = inputs.to(model.device)
        attention_mask = attention_mask.to(model.device)
        
        logger.debug("Generating response...")
        outputs = model.generate(
            inputs,
            attention_mask=attention_mask,
            pad_token_id=tokenizer.pad_token_id,
            max_new_tokens=128,
            do_sample=True,  # Habilitar sampling para respuestas más naturales
            temperature=0.7,  # Controlar la creatividad de las respuestas
            top_p=0.9  # Nucleus sampling
        )
        logger.debug(f"Response generated. Output shape: {outputs.shape}")
        
        response = tokenizer.decode(outputs[0][len(inputs[0]):], skip_special_tokens=True)
        logger.debug(f"Decoded response: {response}")

        return ChatResponse(response=response)
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
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
