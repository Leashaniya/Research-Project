from pathlib import Path
from typing import Dict, Any
from scripts.lectureslide_extract import run_single

def process_lecture_slides(file_path: str) -> Dict[str, Any]:
    pdf_path = Path(file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")
    return run_single(pdf_path)
