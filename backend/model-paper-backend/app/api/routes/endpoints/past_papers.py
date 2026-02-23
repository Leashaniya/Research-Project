from fastapi import APIRouter, UploadFile
import os
from app.core.paths import PAST_PAPERS_DIR

router = APIRouter()

@router.post("/upload")
async def upload_past_paper(file: UploadFile):
    os.makedirs(PAST_PAPERS_DIR, exist_ok=True)

    saved_path = os.path.join(str(PAST_PAPERS_DIR), file.filename)
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    return {
        "status": "uploaded",
        "saved_path": saved_path,
        "message": "Past paper uploaded. Now call /model-paper/generate to run the full pipeline."
    }
