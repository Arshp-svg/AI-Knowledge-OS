import time
import os
from fastapi import APIRouter, Response, status
from app.core.config import settings
from app.core.state import vector_store
from app.services.document_store import document_store

router = APIRouter()
START_TIME = time.time()

@router.get("/health")
def health_check(response: Response):
    uptime_seconds = round(time.time() - START_TIME, 2)
    
    # 1. Check Document Metadata Store (SQLite)
    doc_health = document_store.check_health()
    
    # 2. Check Vector DB (Qdrant Embedded or Remote)
    try:
        qdrant_health = vector_store.check_health()
    except Exception as exc:
        qdrant_health = {"status": "unhealthy", "error": str(exc)}

    # 3. Check LLM Configuration
    has_groq = bool(settings.groq_api_key and settings.groq_api_key.startswith("gsk_"))
    llm_health = {
        "status": "configured" if has_groq else "unconfigured",
        "provider": "groq",
        "model": "openai/gpt-oss-20b"
    }

    # 4. Overall Health Determination
    is_healthy = (
        doc_health.get("status") == "healthy" and
        qdrant_health.get("status") == "healthy" and
        has_groq
    )

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": settings.app_name,
        "version": "1.0.0",
        "uptime_seconds": uptime_seconds,
        "dependencies": {
            "document_store": doc_health,
            "vector_store": qdrant_health,
            "llm": llm_health
        }
    }

