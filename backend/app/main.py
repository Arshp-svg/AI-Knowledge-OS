import uuid
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.security import limiter
from app.api.health import router as health_router
from app.api.document import router as document_router
from app.api.search import router as search_router
from app.api.ask import router as ask_router
from app.api.telemetry import router as telemetry_router

app = FastAPI(
    title=settings.app_name,
    description="Production-grade Retrieval-Augmented Generation (RAG) platform",
    version="1.0.0"
)

# Attach SlowAPI Limiter to Application State
app.state.limiter = limiter

# Custom Rate Limit Exceeded Exception Handler (HTTP 429)
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "RateLimitExceeded",
            "message": "Too many requests. You have exceeded your rate limit. Please try again later.",
            "detail": str(exc.detail)
        }
    )

# Correlation ID & Distributed Tracing Middleware
@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("x-trace-id") or request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(health_router)
app.include_router(document_router)
app.include_router(search_router)
app.include_router(ask_router)
app.include_router(telemetry_router)

@app.get("/")
def root():
    return {
        "app": settings.app_name,
        "status": "online",
        "version": "1.0.0"
    }
