"""Feedback de respuestas (👍/👎) guardado en MongoDB amanda-ia.feedback."""
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)

try:
    from pymongo import MongoClient
    _HAS_PYMONGO = True
except ImportError:
    _HAS_PYMONGO = False


def save_feedback(
    question: str,
    plan: list[str],
    response: str,
    vote: int,
    mode: str | None = None,
) -> bool:
    """
    Guarda feedback en MongoDB amanda-ia.feedback.
    vote: 1 = 👍, -1 = 👎.
    Retorna True si se guardó correctamente.
    """
    if not _HAS_PYMONGO:
        log.warning("pymongo no instalado, feedback no guardado")
        return False
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        log.warning("MONGODB_URI no definido, feedback no guardado")
        return False
    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        db = client["amanda-ia"]
        db["feedback"].insert_one({
            "question": question,
            "plan": plan,
            "response": response,
            "vote": vote,
            "mode": mode,
            "created_at": datetime.now(timezone.utc),
        })
        client.close()
        return True
    except Exception as e:
        log.warning("Error guardando feedback: %s", e)
        return False
