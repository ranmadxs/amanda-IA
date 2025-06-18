from pydantic import BaseModel
from typing import Optional

class ChatRequest(BaseModel):
    """Modelo para las peticiones de chat."""
    message: str

class ChatResponse(BaseModel):
    """Modelo para las respuestas de chat."""
    response: str 