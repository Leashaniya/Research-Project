import os
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# Load .env from service root (works for uvicorn app.main:app, python main.py, Docker, etc.)
from dotenv import load_dotenv
_service_root = Path(__file__).resolve().parent.parent.parent
_env_path = _service_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()

# Fallback: if Google OAuth vars still missing (e.g. BOM/encoding), read .env manually
def _read_env_google_vars():
    if os.getenv("GOOGLE_CLIENT_ID"):
        return
    if not _env_path.exists():
        return
    try:
        raw = _env_path.read_bytes()
        text = raw.decode("utf-8-sig").strip()  # utf-8-sig strips BOM
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key == "GOOGLE_CLIENT_ID" and value and not os.getenv("GOOGLE_CLIENT_ID"):
                    os.environ["GOOGLE_CLIENT_ID"] = value
                elif key == "GOOGLE_CLIENT_SECRET" and value and not os.getenv("GOOGLE_CLIENT_SECRET"):
                    os.environ["GOOGLE_CLIENT_SECRET"] = value
    except Exception:
        pass
_read_env_google_vars()


def _infer_default_session_cookie_secure() -> bool:
    explicit = os.getenv("SESSION_COOKIE_SECURE")
    if explicit is not None:
        return explicit.lower() == "true"
    for url in (os.getenv("REDIRECT_URI", ""), os.getenv("FRONTEND_URL", "")):
        if url.strip().lower().startswith("https://"):
            return True
    return False

# Single output dir for TTS WAV files (used by tts_tool and main.py static mount)
AUDIO_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "audio"
AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    # Application Configuration
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Google OAuth Configuration
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    
    # OAuth URLs
    # REDIRECT_URI: must be the exact callback URL (same origin as login). If unset, built from request (use when behind a proxy).
    REDIRECT_URI: str = os.getenv("REDIRECT_URI", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")
    
    # OpenAI API Key
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # OpenAI Model Configuration
    RAG_SUMMARY_MODEL: str = os.getenv("RAG_SUMMARY_MODEL", "gpt-4o-mini")

    # CA guidance crew: chat model and output budget (reduces truncation on long assignments)
    CA_GUIDANCE_MODEL: str = os.getenv("CA_GUIDANCE_MODEL", "gpt-4o-mini")
    CA_GUIDANCE_MAX_OUTPUT_TOKENS: int = int(os.getenv("CA_GUIDANCE_MAX_OUTPUT_TOKENS", "16384"))
    CA_GUIDANCE_CHUNK_MAX_CHARS: int = int(os.getenv("CA_GUIDANCE_CHUNK_MAX_CHARS", "14000"))
    
    # MongoDB Configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "ca_guidance_db")
    
    # Image Explanation Configuration
    ENABLE_IMAGE_EXPLANATIONS: bool = os.getenv("ENABLE_IMAGE_EXPLANATIONS", "true").lower() == "true"

    # CA guidance: generate PNG diagrams (ER, flowchart) via OpenAI Images API when the assignment asks for visuals
    ENABLE_ASSIGNMENT_DIAGRAM_IMAGES: bool = os.getenv(
        "ENABLE_ASSIGNMENT_DIAGRAM_IMAGES", "true"
    ).lower() == "true"
    ASSIGNMENT_DIAGRAM_IMAGE_MODEL: str = os.getenv("ASSIGNMENT_DIAGRAM_IMAGE_MODEL", "dall-e-3")
    # Chat model for conceptual ER diagrams as Graphviz DOT (traditional symbols), not DALL·E
    ASSIGNMENT_ER_GRAPHVIZ_MODEL: str = os.getenv("ASSIGNMENT_ER_GRAPHVIZ_MODEL", "gpt-4o-mini")

    # Session cookie configuration for OAuth and cross-site login flows
    SESSION_COOKIE_SECURE: bool = _infer_default_session_cookie_secure()
    SESSION_COOKIE_NAME: str = os.getenv("SESSION_COOKIE_NAME", "session")
    SESSION_COOKIE_DOMAIN: Optional[str] = os.getenv("SESSION_COOKIE_DOMAIN", "") or None

    # TTS (Piper) – required for summarization audio. If unset, summaries have no audio.
    # Example: PIPER_EXE=/path/to/piper, PIPER_MODEL=/path/to/model.onnx
    PIPER_EXE: str = os.getenv("PIPER_EXE", "")
    PIPER_MODEL: str = os.getenv("PIPER_MODEL", "")

settings = Settings()

