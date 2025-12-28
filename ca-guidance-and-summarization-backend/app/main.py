import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings
from app.api.routes import auth, public, protected
from fastapi.staticfiles import StaticFiles

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

app.mount("/audio", StaticFiles(directory="outputs/audio"), name="audio")

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

