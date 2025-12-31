# from fastapi import APIRouter, UploadFile
# import os

# from app.services import slides_service
# from app.core.paths import SLIDES_DIR

# router = APIRouter()

# @router.post("/upload")
# async def upload_lecture_slide(file: UploadFile):
#     # Ensure the directory exists
#     os.makedirs(SLIDES_DIR, exist_ok=True)

#     # Save the uploaded file
#     saved_path = os.path.join(SLIDES_DIR, file.filename)
#     with open(saved_path, "wb") as f:
#         f.write(await file.read())

#     # Process the lecture slides
#     output_paths = slides_service.process_lecture_slides(saved_path)

#     return {
#         "status": "success",
#         "saved_path": saved_path,
#         "output_paths": output_paths
#     }

from fastapi import APIRouter, UploadFile
import os

from app.services import slides_service, structure_service, generation_service
from app.core.paths import SLIDES_DIR

router = APIRouter()

@router.post("/upload")
async def upload_lecture_slide(file: UploadFile):
    os.makedirs(SLIDES_DIR, exist_ok=True)

    saved_path = os.path.join(str(SLIDES_DIR), file.filename)
    with open(saved_path, "wb") as f:
        f.write(await file.read())

    # 1) Extract slides + rebuild embeddings/index
    slides_outputs = slides_service.process_lecture_slides(saved_path)

    # 2) Ensure blueprint/template_questions exist (if not, create)
    structure_outputs = structure_service.ensure_structure_artifacts()

    # 3) Generate model paper
    model_outputs = generation_service.generate_model_paper()

    return {
        "status": "success",
        "saved_path": saved_path,
        "slides_outputs": slides_outputs,
        "structure_outputs": structure_outputs,
        "model_paper_outputs": model_outputs
    }