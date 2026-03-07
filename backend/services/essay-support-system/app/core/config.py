"""
Configuration module for the Adaptive Learning System.
Loads settings from environment variables and .env file.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the service root directory (two levels up from this file)
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)


class Settings:
    # ─── Project Paths ────────────────────────────────────────────
    SERVICE_ROOT: Path = Path(__file__).resolve().parent.parent.parent
    DATA_DIR: Path = SERVICE_ROOT / "Data"
    BLOOM_DATASET_DIR: Path = SERVICE_ROOT / "bloomsDataset"
    RL_FILE: Path = SERVICE_ROOT / "rl.pkl"
    LOG_FILE: Path = SERVICE_ROOT / "attempt_log.csv"
    # EXTRACTION_LOG_FILE: Path = Path("C:/Users/PC/Videos/Research-Project/backend/services/essay-support-system/extracted_questions.log")
    EXTRACTION_LOG_FILE: Path = SERVICE_ROOT /"extracted_questions.log"
    BLOOM_MODEL_PATH: Path = SERVICE_ROOT / "scripts" / "bloom_model.pkl"
    LECTURE_DIR: Path = SERVICE_ROOT / "Data" / "Lecture_Notes"

    # ─── RL Hyperparameters ──────────────────────────────────────
    ALPHA: float = 0.5
    GAMMA: float = 0.9

    # ─── OpenAI ───────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
    BLOOM_CLASSIFIER_TEMPERATURE: float = float(os.getenv("BLOOM_CLASSIFIER_TEMPERATURE", "0.2"))

    # ─── Server ───────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # ─── Evaluation ───────────────────────────────────────────────
    # Score threshold at/above which an answer is treated as "correct".
    CORRECTNESS_THRESHOLD: float = float(os.getenv("CORRECTNESS_THRESHOLD", "75"))

    # ─── CORS ─────────────────────────────────────────────────────
    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]


settings = Settings()

# ─── Ensure directories exist ─────────────────────────────────
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
