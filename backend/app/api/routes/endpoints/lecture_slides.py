from fastapi import APIRouter, UploadFile
import os

from app.services import slides_service
from app.core.paths import SLIDES_DIR

router = APIRouter()

@router.post("/upload")
async def upload_lecture_slide(file: UploadFile):
    # Ensure the directory exists
    os.makedirs(SLIDES_DIR, exist_ok=True)

    # Save the uploaded file
    saved_path = os.path.join(SLIDES_DIR, file.filename)
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    # Process the lecture slides
    output_paths = slides_service.process_lecture_slides(saved_path)

    return {
        "status": "success",
        "saved_path": saved_path,
        "output_paths": output_paths
    }