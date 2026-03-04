"""
FastAPI application — Adaptive Learning System

Mirrors every endpoint from the original Flask app.py with
identical business logic, but uses FastAPI + Pydantic models
and the updated OpenAI SDK (≥1.0).

Endpoints
---------
GET   /api/health               → liveness probe
POST  /api/sessions/start       → start a new learning session
POST  /api/sessions/reset       → reset an existing session
POST  /api/questions/next       → get the next adaptive question
POST  /api/answers/submit       → submit & evaluate an answer
GET   /api/stats                → session statistics
GET   /api/pdfs/check           → list available PDFs
GET   /api/history              → CSV attempt log as JSON
GET   /api/analytics/overview   → aggregated analytics data
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.services.question_bank import question_bank
from app.api.routes import router as api_router


# ═══════════════════════════════════════════════════════════════
#  Lifespan — load question bank once on startup
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🔄 Loading question bank …")
    question_bank.load()
    print(f"✅ Question bank ready – {question_bank.count} questions")
    yield
    print("🛑 Shutting down …")


# ═══════════════════════════════════════════════════════════════
#  App & middleware
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="Adaptive Learning System",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all API routes
app.include_router(api_router)
