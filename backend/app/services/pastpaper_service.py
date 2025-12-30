# Service for OCR and blueprint extraction logic

import os
from pathlib import Path
from typing import Dict, Any
from scripts.pastpaper_extract import run_single



def process_past_paper(file_path: str) -> Dict[str, Any]:
    """
    Process a single uploaded past paper PDF.

    Called by FastAPI endpoint after saving the file.
    """
    pdf_path = Path(file_path)

    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    # Run single-PDF pipeline (API-safe)
    result = run_single(
        pdf_path=pdf_path,
        run_qc=False  # IMPORTANT: keep False for API usage
    )

    return result
