import logging
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import settings, AUDIO_OUTPUT_DIR
from app.api.routes import auth, er, public, protected, summaries
from fastapi.staticfiles import StaticFiles
from pathlib import Path


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown: close MongoDB on exit so Ctrl+C doesn't hang on PyMongo threads."""
    # Validate Google OAuth config so we fail fast with a clear message
    if settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET:
        logger.info("Google OAuth configured (client_id present)")
    else:
        logger.warning(
            "Google OAuth not configured (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET missing in .env). "
            "Sign-in with Google will fail. See .env.example for setup."
        )
    # Log TTS (Piper) availability so we know why audio may be missing after summarization
    piper_exe = (getattr(settings, "PIPER_EXE", None) or "").strip()
    piper_model = (getattr(settings, "PIPER_MODEL", None) or "").strip()
    if piper_exe and piper_model and Path(piper_exe).exists():
        logger.info("TTS (Piper) available: audio will be generated for summaries")
    else:
        logger.warning(
            "TTS (Piper) not available (PIPER_EXE=%s, PIPER_MODEL set=%s, exe exists=%s). "
            "Summaries will have no audio.",
            "set" if piper_exe else "unset",
            "yes" if piper_model else "no",
            Path(piper_exe).exists() if piper_exe else False,
        )
    yield
    from app.core.database import close_database
    close_database()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG to see all messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Set specific loggers to appropriate levels
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)
# Suppress verbose PyMongo/MongoDB driver logs (heartbeats, etc.)
logging.getLogger("pymongo").setLevel(logging.WARNING)
logging.getLogger("pymongo.topology").setLevel(logging.WARNING)

# Create FastAPI instance
app = FastAPI(
    title="CA Guidance Prototype API",
    description="A FastAPI application for CA guidance prototype with Google OAuth",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve TTS audio files from the same dir used by tts_tool
app.mount("/audio", StaticFiles(directory=str(AUDIO_OUTPUT_DIR)), name="audio")

# Add session middleware for OAuth (state is stored in session for CSRF check on callback)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    path="/",
    same_site="lax",
    max_age=14 * 24 * 60 * 60,
)

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

# Register exception handler BEFORE including routers
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors and log them for debugging."""
    errors = exc.errors()
    # Log detailed error information - use print to ensure it shows up
    print("\n" + "=" * 80)
    print(f"VALIDATION ERROR on {request.url.path}")
    print(f"Method: {request.method}")
    print(f"Errors:")
    print(json.dumps(errors, indent=2))
    print("=" * 80 + "\n")
    logger.error("=" * 80)
    logger.error(f"VALIDATION ERROR on {request.url.path}")
    logger.error(f"Method: {request.method}")
    logger.error(f"Errors: {json.dumps(errors, indent=2)}")
    logger.error("=" * 80)
    
    # Return detailed error response
    return JSONResponse(
        status_code=422,
        content={
            "detail": errors,
            "message": "Validation failed. Check the 'detail' field for specific errors."
        }
    )

app.add_exception_handler(RequestValidationError, validation_exception_handler)

# Include routers
app.include_router(public.router)
app.include_router(auth.router)
app.include_router(protected.router)
app.include_router(summaries.router)
app.include_router(er.router)

