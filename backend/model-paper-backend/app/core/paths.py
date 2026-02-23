# import os

# # Base data directory
# DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

# # Subdirectories
# PAST_PAPERS_DIR = os.path.join(DATA_DIR, "past_paper_red_box")
# SLIDES_DIR = os.path.join(DATA_DIR, "lectureslides")
# TEXT_EXTRACTION_DIR = os.path.join(DATA_DIR, "text_extraction_hybrid")
# TMP_PAGES_DIR = os.path.join(DATA_DIR, "_tmp_pdf_pages_hybrid")
# SLIDES_EXTRACTION_DIR = os.path.join(DATA_DIR, "lecture_slides_extraction")
# SLIDES_EMB_DIR = os.path.join(DATA_DIR, "slides_embeddings")
# ARTIFACTS_DIR = os.path.join(DATA_DIR, "artifacts")
# OUTPUTS_DIR = os.path.join(DATA_DIR, "outputs")

from pathlib import Path

# PROJECT ROOT = .../Research Project
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core -> app -> backend -> project_root
DATA_DIR = PROJECT_ROOT / "data"

PAST_PAPERS_DIR = DATA_DIR / "past_paper_red_box"
SLIDES_DIR = DATA_DIR / "lectureslides"
TEXT_EXTRACTION_DIR = DATA_DIR / "text_extraction_hybrid"
TMP_PAGES_DIR = DATA_DIR / "_tmp_pdf_pages_hybrid"
SLIDES_EXTRACTION_DIR = DATA_DIR / "lecture_slides_extraction"
SLIDES_EMB_DIR = DATA_DIR / "slides_embeddings"
ARTIFACTS_DIR = DATA_DIR / "artifacts"
OUTPUTS_DIR = DATA_DIR / "outputs"

# Correcting the variable name from DATA_ROOT to DATA_DIR
# Replace DATA_ROOT with DATA_DIR in the script
# Example usage:
# print('DATA_DIR:', DATA_DIR)
