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
    BLOOM_MODEL_PATH: Path = SERVICE_ROOT / "bloom_model.pkl"
    LECTURE_DIR: Path = SERVICE_ROOT / "Data" / "Lecture_Notes"

    # ─── RL Hyperparameters ──────────────────────────────────────
    ALPHA: float = 0.5
    GAMMA: float = 0.9

    # ─── OpenAI ───────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # ─── Server ───────────────────────────────────────────────────
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

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
