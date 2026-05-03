from fastapi import APIRouter, UploadFile, HTTPException
import os
from app.core.paths import SLIDES_DIR

router = APIRouter()

ALLOWED_EXTENSIONS = (".pdf", ".PDF")

def _is_pdf(filename: str) -> bool:
    return filename and any(filename.endswith(ext) for ext in ALLOWED_EXTENSIONS)

@router.post("/upload")
async def upload_lecture_slide(file: UploadFile):
    if not file.filename or not _is_pdf(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Only PDF format is allowed for lecture slides. Please upload a .pdf file."
        )

    # Ensure the directory for storing files exists.
    os.makedirs(SLIDES_DIR, exist_ok=True)

    # Define the path where the file will be saved.
    saved_path = os.path.join(str(SLIDES_DIR), file.filename)

    # Save the uploaded file to the specified path.
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    return {
        "status": "uploaded",
        "saved_path": saved_path,
        "message": "Lecture slide uploaded. Now call /model-paper/generate to run the full pipeline."
    }
