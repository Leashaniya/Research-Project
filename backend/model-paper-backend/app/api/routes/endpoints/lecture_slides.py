from fastapi import APIRouter, UploadFile
import os
from app.core.paths import SLIDES_DIR

router = APIRouter()

@router.post("/upload")
async def upload_lecture_slide(file: UploadFile):
    os.makedirs(SLIDES_DIR, exist_ok=True)

    saved_path = os.path.join(str(SLIDES_DIR), file.filename)
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    return {
        "status": "uploaded",
        "saved_path": saved_path,
        "message": "Lecture slide uploaded. Now call /model-paper/generate to run the full pipeline."
    }
