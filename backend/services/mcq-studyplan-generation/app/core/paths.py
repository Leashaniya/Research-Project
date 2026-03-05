"""Path configuration for MCQ Study Plan service."""
from pathlib import Path

# Service root = mcq-studyplan-generation/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

LECTURE_SLIDES_DIR = PROJECT_ROOT / "Lecture_slides"
QUESTIONS_DIR = PROJECT_ROOT / "Questions"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
STATIC_DIR = PROJECT_ROOT / "static"
