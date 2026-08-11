from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables from .env file
# Try to find .env in model-paper-backend directory first, then project root
# __file__ = .../backend/model-paper-backend/app/core/config.py
backend_dir = Path(__file__).resolve().parents[2]  # -> .../backend/model-paper-backend
env_path = backend_dir / ".env"
if not env_path.exists():
    # Try project root: parent of backend directory
    project_root = backend_dir.parents[1]          # -> .../Research Project
    env_path = project_root / ".env"

if env_path.exists():
    load_dotenv(dotenv_path=str(env_path), override=True)
    print(f"[CONFIG] Loaded .env from: {env_path}")
else:
    # Fallback to default behavior (current directory / process cwd)
    load_dotenv(override=True)
    print(f"[CONFIG] Using default .env loading (current directory)")

# Retrieve the OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()  # Strip whitespace
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() if os.getenv("OPENAI_BASE_URL") else None  # Optional: For Local LLM

# =========================
# Hard constraints (do not infer from artifacts)
# =========================
# Single source of truth: model paper must ALWAYS have exactly 4 questions.
MODEL_PAPER_QUESTION_COUNT = 4

class Settings:
    OPENAI_API_KEY = OPENAI_API_KEY
    OPENAI_BASE_URL = OPENAI_BASE_URL
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    # LLM Provider Config
    # Always use OpenAI - Azure support is disabled
    LLM_PROVIDER = "openai"  # Always use OpenAI, ignore LLM_PROVIDER env var
    # Azure OpenAI Config (kept for backward compatibility but not used)
    AZURE_OPENAI_API_KEY = None
    AZURE_OPENAI_ENDPOINT = None
    AZURE_DEPLOYMENT_NAME = None
    AZURE_API_VERSION = None
    
    # MongoDB Config
    MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://it22891440_db_user:leasha@cluster0.nrfff5z.mongodb.net/?appName=Cluster0")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "pastpaper_db")
    
    # Blueprint Validation Config
    MIN_SLOTS = int(os.getenv("MIN_SLOTS", 4))  # Minimum question slots in blueprint
    DEFAULT_SLOT_MARKS = int(os.getenv("DEFAULT_SLOT_MARKS", 25))  # Default marks per slot

    # Hard constraint for generation (do NOT infer from blueprint/template artifacts)
    MODEL_PAPER_QUESTION_COUNT = MODEL_PAPER_QUESTION_COUNT
    
    # Critic Validation Config
    MIN_SCENARIO_CHARS = int(os.getenv("MIN_SCENARIO_CHARS", 120))  # Minimum scenario length in characters
    MIN_SCENARIO_TOKENS = int(os.getenv("MIN_SCENARIO_TOKENS", 25))  # Minimum scenario length in tokens (approx)
    
    # Fallback Config
    FALLBACK_REBUILDS_MAX = int(os.getenv("FALLBACK_REBUILDS_MAX", 2))  # Maximum fallback rebuild attempts


    def validate_openai_key(self):
        # Always validate OpenAI API key (Azure is not used)
        if not self.OPENAI_API_KEY:
             raise ValueError("OpenAI API Key is missing. Please set OPENAI_API_KEY in your .env file.")

settings = Settings()