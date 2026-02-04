from fastapi import APIRouter
import os
from pathlib import Path
from typing import List, Dict
from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR

router = APIRouter()

def _list_pdfs(folder: Path) -> List[str]:
    """
    Return PDF filenames in `folder` with case-insensitive extension matching.
    This avoids missing files like *.Pdf on Windows.
    """
    if not folder.exists():
        return []

    out: List[str] = []
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() == ".pdf":
            out.append(f.name)
    return sorted(list(set(out)))

@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=True)
async def list_files() -> Dict[str, List[str]]:
    """
    List all uploaded files in past papers and slides directories.
    Useful for demonstrating the upload functionality works.
    """
    
    # Ensure directories exist (just in case)
    os.makedirs(PAST_PAPERS_DIR, exist_ok=True)
    os.makedirs(SLIDES_DIR, exist_ok=True)
    
    past_papers_path = Path(PAST_PAPERS_DIR)
    slides_path = Path(SLIDES_DIR)
    
    past_papers = _list_pdfs(past_papers_path)
    lecture_slides = _list_pdfs(slides_path)
    
    # Debug logging
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"PAST_PAPERS_DIR: {PAST_PAPERS_DIR}, exists: {past_papers_path.exists()}")
    logger.info(f"SLIDES_DIR: {SLIDES_DIR}, exists: {slides_path.exists()}")
    logger.info(f"Found {len(past_papers)} past papers: {past_papers}")
    logger.info(f"Found {len(lecture_slides)} lecture slides: {lecture_slides}")
    
    return {
        "past_papers": past_papers,
        "lecture_slides": lecture_slides,
    }
