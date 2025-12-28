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
    REDIRECT_URI: str = os.getenv("REDIRECT_URI", "")
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "")
    
    # OpenAI API Key
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Local LLM / Ollama
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    RAG_SUMMARY_PROVIDER: str = os.getenv("RAG_SUMMARY_PROVIDER", "openai")
    RAG_SUMMARY_MODEL: str = os.getenv("RAG_SUMMARY_MODEL", "gpt-4o-mini") 

settings = Settings()

