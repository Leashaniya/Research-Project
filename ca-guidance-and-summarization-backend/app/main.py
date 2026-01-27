import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
from app.api.routes import auth, er, public, protected, summaries
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI instance
app = FastAPI(
    title="CA Guidance Prototype API",
    description="A FastAPI application for CA guidance prototype with Google OAuth",
    version="1.0.0"
)

# Ensure audio directory exists
AUDIO_DIR = Path("outputs/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

#Serve audio files
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")

# Add session middleware for OAuth
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Add CORS middleware
# Allow both production and development frontend URLs
allowed_origins = [
    settings.FRONTEND_URL,
    "http://ca.vuedapt.com",
    "https://ca.vuedapt.com",
    "http://localhost:3000",
    "http://localhost:3333",  # Vite dev server port
    "http://localhost:5173",  # Vite default dev server port
    "http://localhost:5174",  # Vite alternate port (common when 5173 is busy)
]

# Remove None/empty values
allowed_origins = [origin for origin in allowed_origins if origin]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(protected.router)
app.include_router(summaries.router)
app.include_router(er.router)

