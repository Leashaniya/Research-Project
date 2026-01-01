from fastapi import APIRouter
import os
from pathlib import Path
from typing import List, Dict
from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR

router = APIRouter()

@router.get("/")
async def list_files() -> Dict[str, List[str]]:
    """
    List all uploaded files in past papers and slides directories.
    Useful for demonstrating the upload functionality works.
    """
    
    # Ensure directories exist (just in case)
    os.makedirs(PAST_PAPERS_DIR, exist_ok=True)
    os.makedirs(SLIDES_DIR, exist_ok=True)
    
    past_papers = [
        f.name for f in Path(PAST_PAPERS_DIR).glob("*.pdf") 
    ] + [
        f.name for f in Path(PAST_PAPERS_DIR).glob("*.PDF")
    ]
    
    slides = [
        f.name for f in Path(SLIDES_DIR).glob("*.pdf")
    ] + [
        f.name for f in Path(SLIDES_DIR).glob("*.PDF")
    ]
    
    return {
        "past_papers": sorted(list(set(past_papers))),
        "lecture_slides": sorted(list(set(slides)))
    }
