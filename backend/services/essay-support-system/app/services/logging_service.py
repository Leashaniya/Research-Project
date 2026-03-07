"""
Attempt Logging  (from app.py log_attempt / services.py)
"""

import csv
from datetime import datetime
from typing import List

from app.core.config import settings


def log_attempt(
    attempt_no: int,
    topic: str,
    difficulty: str,
    behaviour: dict,
    reward: float,
    score: float,
):
    """Append an attempt row to the CSV log (same columns as app.py)."""
    file_exists = settings.LOG_FILE.exists()
    with open(settings.LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "timestamp", "attempt", "topic", "difficulty",
                "concepts", "mistakes", "answer_length", "reward", "score",
            ])
        writer.writerow([
            datetime.now().isoformat(),
            attempt_no,
            topic,
            difficulty,
            behaviour.get("concept_count", 0),
            behaviour.get("mistakes", 0),
            behaviour.get("answer_length", 0),
            reward,
            score,
        ])


def get_attempt_history() -> List[dict]:
    """Read the full attempt log CSV and return as list of dicts."""
    if not settings.LOG_FILE.exists():
        return []
    history: List[dict] = []
    with open(settings.LOG_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            history.append(dict(row))
    return history
