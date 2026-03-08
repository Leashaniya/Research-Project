import os
from typing import Optional

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
    
    # MongoDB Configuration
    MONGO_URI: str = os.getenv("MONGO_URI", "")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "ca_guidance_db")
    
    # Image Explanation Configuration
    ENABLE_IMAGE_EXPLANATIONS: bool = os.getenv("ENABLE_IMAGE_EXPLANATIONS", "true").lower() == "true"

    # TTS (Piper) – required for summarization audio. If unset, summaries have no audio.
    # Example: PIPER_EXE=/path/to/piper, PIPER_MODEL=/path/to/model.onnx
    PIPER_EXE: str = os.getenv("PIPER_EXE", "")
    PIPER_MODEL: str = os.getenv("PIPER_MODEL", "")

settings = Settings()

