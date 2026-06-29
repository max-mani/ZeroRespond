# backend/app/main.py
import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from app.services.alert_queue import queue_worker
from app.routers import alerts, cases, auth, reports, org 

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="ZeroRespond API",
    description="AI-Enhanced Incident Response Platform — DPDP Compliant",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        errors.append({
            "field": " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    return JSONResponse(status_code=422, content={"error": "Validation failed", "detail": errors})

@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"error": "Database constraint violation", "detail": str(exc.orig)})

# ─── Lifespan: start queue worker on boot ────────────────────────────────────

_worker_task = None

@app.on_event("startup")
async def startup_event():
    global _worker_task
    _worker_task = asyncio.create_task(queue_worker())
    logger.info("ZeroRespond API started — queue worker running.")

@app.on_event("shutdown")
async def shutdown_event():
    global _worker_task
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
    logger.info("ZeroRespond API shutting down — queue worker stopped.")

# ─── Routers ─────────────────────────────────────────────────────────────────

app.include_router(auth.router)
app.include_router(alerts.router)
app.include_router(cases.router)
app.include_router(reports.router)
app.include_router(org.router)

@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "ok",
        "version": "1.0.0",
        "environment": "development"
    }

# Add to backend/app/main.py

from app.services.ai_agent import check_ollama_health

@app.get("/health/ai", tags=["System"])
async def ai_health_check():
    """
    Check AI agent status — Ollama running, model available, queue depth.
    Use this to verify the AI enrichment pipeline is healthy.
    """
    ai_status = await check_ollama_health()
    return {
        "status": "ok" if ai_status["status"] == "ready" else "degraded",
        "ai_agent": ai_status,
        "fallback": "rule-based classifier active when AI unavailable"
    }