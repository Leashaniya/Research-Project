from fastapi import APIRouter, UploadFile, HTTPException
import os
from app.core.paths import PAST_PAPERS_DIR

router = APIRouter()

ALLOWED_EXTENSIONS = (".pdf", ".PDF")

def _is_pdf(filename: str) -> bool:
    return filename and any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)

@router.post("/upload")
async def upload_past_paper(file: UploadFile):
    if not file.filename or not _is_pdf(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Only PDF format is allowed for past papers. Please upload a .pdf file."
        )

    # Ensure the directory for storing files exists.
    os.makedirs(PAST_PAPERS_DIR, exist_ok=True)

    # Define the path where the file will be saved.
    saved_path = os.path.join(str(PAST_PAPERS_DIR), file.filename)

    # Save the uploaded file to the specified path.
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    return {
        "status": "uploaded",
        "saved_path": saved_path,
        "message": "Past paper uploaded. Now call /model-paper/generate to run the full pipeline."
    }
