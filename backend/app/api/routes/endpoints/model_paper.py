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

@router.get("/diagram-image")
async def get_diagram_image(question_no: str = None):
    """Get the diagram image for a specific question (e.g., Q1)."""
    import json
    
    # Load the paper JSON to get diagram path
    json_path = os.path.join(str(OUTPUTS_DIR), "model_papers", "agentic_model_paper.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Paper not found")
    
    with open(json_path, "r", encoding="utf-8") as f:
        paper_data = json.load(f)
    
    # Find the question with the diagram
    diagram_path = None
    if question_no:
        for q in paper_data.get("questions", []):
            if q.get("question_no") == question_no.upper() and q.get("diagram_image_path"):
                diagram_path = q.get("diagram_image_path")
                break
    else:
        # If no question_no specified, find first question with diagram
        for q in paper_data.get("questions", []):
            if q.get("diagram_image_path"):
                diagram_path = q.get("diagram_image_path")
                break
    
    if not diagram_path or not os.path.exists(diagram_path):
        raise HTTPException(status_code=404, detail="Diagram not found")
    
    return FileResponse(diagram_path, media_type="image/png")