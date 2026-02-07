from fastapi import FastAPI
from app.core.config import settings
from app.api.health import router as health_router
from app.api.document import router as document_router
from app.api.search import router as search_router
from app.api.ask import router as ask_router


app = FastAPI(title=settings.app_name)

app.include_router(health_router)
app.include_router(document_router)
app.include_router(search_router)
app.include_router(ask_router)

@app.get("/")
def root():
    return {"message": "AI Knowledge OS backend running"}
