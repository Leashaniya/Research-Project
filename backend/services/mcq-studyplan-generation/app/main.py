"""MCQ Study Plan Generation - FastAPI application."""
import os
import sys
from pathlib import Path

# Ensure service root is in path for config, pdf_utils, etc.
SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

# Create outputs dir
os.makedirs("outputs", exist_ok=True)
os.makedirs("Lecture_slides", exist_ok=True)
os.makedirs("Questions", exist_ok=True)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router

app = FastAPI(
    title="MCQ Study Plan Generation API",
    description="Generate adaptive study plans from lecture materials and question patterns",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Mount static and outputs for graph HTML
if (SERVICE_ROOT / "static").exists():
    app.mount("/static", StaticFiles(directory=str(SERVICE_ROOT / "static")), name="static")
if (SERVICE_ROOT / "outputs").exists():
    app.mount("/outputs", StaticFiles(directory=str(SERVICE_ROOT / "outputs")), name="outputs")


@app.get("/")
def root():
    return RedirectResponse(url="/docs")
