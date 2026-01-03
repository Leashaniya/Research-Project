from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.services import pipeline_service
from app.core.paths import OUTPUTS_DIR
import os

router = APIRouter()

@router.post("/process-files")
async def process_files():
    """Step 1: Process uploads, extract text, and build templates."""
    res = await pipeline_service.process_uploaded_files()
    if res["status"] == "error":
        raise HTTPException(status_code=500, detail=res["message"])
    return res

@router.post("/generate-paper")
async def generate_paper():
    """Runs the COMPLETE pipeline: Extraction -> Blueprinting -> AI Generation."""
    res = await pipeline_service.run_full_pipeline()
    if res["status"] == "error":
        raise HTTPException(status_code=500, detail=res["message"])
    return res

@router.get("/paper-json")
async def get_paper_json():
    """Get the latest generated JSON paper."""
    path = os.path.join(str(OUTPUTS_DIR), "model_papers", "agentic_model_paper.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Paper not found")
    import json
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("/download-pdf")
async def download_pdf():
    """Download the latest generated PDF paper."""
    path = os.path.join(str(OUTPUTS_DIR), "model_papers", "agentic_model_paper.pdf")
    if not os.path.exists(path):
        # Try to rebuild it if JSON exists
        json_path = path.replace(".pdf", ".json")
        if os.path.exists(json_path):
            from app.services.pdf_service import PDFService
            import json
            with open(json_path, "r", encoding="utf-8") as f:
                 PDFService.generate_pdf(json.load(f), path)
        else:
            raise HTTPException(status_code=404, detail="PDF not found. Please generate the paper first.")
    
    return FileResponse(path, filename="Model_Paper.pdf", media_type="application/pdf")
