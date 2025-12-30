from fastapi import APIRouter, UploadFile
import os

from app.services import pastpaper_service
from app.core.paths import PAST_PAPERS_DIR

router = APIRouter()

@router.post("/upload")
async def upload_past_paper(file: UploadFile):
    # Ensure the directory exists
    os.makedirs(PAST_PAPERS_DIR, exist_ok=True)

    # Save the uploaded file
    saved_path = os.path.join(PAST_PAPERS_DIR, file.filename)
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    # Process the past paper
    outputs = pastpaper_service.process_past_paper(saved_path)

    return {
        "status": "success",
        "saved_path": saved_path,
        "outputs": outputs
    }