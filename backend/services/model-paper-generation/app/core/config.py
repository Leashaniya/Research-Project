from dotenv import load_dotenv
import os
from pathlib import Path

# Load environment variables from .env file
# Try to find .env in service root (model-paper-generation)
service_root = Path(__file__).resolve().parents[2]  # app/core -> app -> service_root
env_path = service_root / ".env"
if not env_path.exists():
    # Try parent of service root
    env_path = service_root.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=str(env_path), override=True)
    print(f"[CONFIG] Loaded .env from: {env_path}")
else:
    # Fallback to default behavior (current directory)
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
    # Paper B (questions_only): stem weight must match Paper A final-exam level (not drill intros)
    PAPER_B_MIN_ER_STEM_CHARS = int(os.getenv("PAPER_B_MIN_ER_STEM_CHARS", 400))
    PAPER_B_MIN_ER_STEM_SENTENCES = int(os.getenv("PAPER_B_MIN_ER_STEM_SENTENCES", 4))
    PAPER_B_ER_RICHNESS_GROUPS_MIN = int(os.getenv("PAPER_B_ER_RICHNESS_GROUPS_MIN", 2))
    # Non-ER (normalization, SQL, RA, theory, etc.)
    PAPER_B_MIN_NON_ER_STEM_CHARS = int(os.getenv("PAPER_B_MIN_NON_ER_STEM_CHARS", 300))
    PAPER_B_MIN_NON_ER_STEM_SENTENCES = int(os.getenv("PAPER_B_MIN_NON_ER_STEM_SENTENCES", 3))
    PAPER_B_MIN_NON_ER_STEM_WORDS = int(os.getenv("PAPER_B_MIN_NON_ER_STEM_WORDS", 60))
    # Normalization: allow FD-dense single block (few sentence boundaries) if enough FD arrows + length
    PAPER_B_MIN_NORM_STEM_CHARS = int(os.getenv("PAPER_B_MIN_NORM_STEM_CHARS", 240))
    PAPER_B_MIN_NORM_FD_ARROWS = int(os.getenv("PAPER_B_MIN_NORM_FD_ARROWS", 2))
    
    # Fallback Config
    FALLBACK_REBUILDS_MAX = int(os.getenv("FALLBACK_REBUILDS_MAX", 2))  # Maximum fallback rebuild attempts


    def validate_openai_key(self):
        # Always validate OpenAI API key (Azure is not used)
        if not self.OPENAI_API_KEY:
             raise ValueError("OpenAI API Key is missing. Please set OPENAI_API_KEY in your .env file.")

settings = Settings()