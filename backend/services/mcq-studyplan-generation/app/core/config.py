"""Configuration for MCQ Study Plan service."""
from pathlib import Path
import os

# Try to load .env from service root
try:
    from dotenv import load_dotenv
    service_root = Path(__file__).resolve().parents[2]
    env_path = service_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=str(env_path), override=True)
    else:
        load_dotenv(override=True)
except ImportError:
    pass

# Folder paths (relative to PROJECT_ROOT, resolved in paths.py)
LECTURE_SLIDES_FOLDER = os.getenv("LECTURE_SLIDES_FOLDER", "Lecture_slides")
QUESTIONS_FOLDER = os.getenv("QUESTIONS_FOLDER", "Questions")

# Processing parameters
N_TOPICS = int(os.getenv("N_TOPICS", "6"))
TOP_KEYWORDS_PER_TOPIC = int(os.getenv("TOP_KEYWORDS_PER_TOPIC", "5"))
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.30"))
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")
MAX_SENTENCES_PER_LECTURE = int(os.getenv("MAX_SENTENCES_PER_LECTURE", "100"))

# Study plan parameters
DEFAULT_STUDY_HOURS_PER_DAY = int(os.getenv("DEFAULT_STUDY_HOURS_PER_DAY", "2"))
DEFAULT_TOTAL_STUDY_DAYS = int(os.getenv("DEFAULT_TOTAL_STUDY_DAYS", "7"))

# OpenAI (from env, not hardcoded)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
