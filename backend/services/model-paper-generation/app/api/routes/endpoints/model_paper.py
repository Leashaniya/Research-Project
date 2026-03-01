import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from app.services import pipeline_service
from app.core.paths import OUTPUTS_DIR
import os

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/process-files")
async def process_files():
    """Step 1: Process uploads, extract text, and build templates."""
    res = await pipeline_service.process_uploaded_files()
    if res["status"] == "error":
        logger.error("process-files failed: %s", res.get("message"), exc_info=True)
        raise HTTPException(status_code=500, detail=res["message"])
    return res

@router.post("/generate-paper")
async def generate_paper():
    """Runs the COMPLETE pipeline: Extraction -> Blueprinting -> AI Generation."""
    res = await pipeline_service.run_full_pipeline()
    if res["status"] == "error":
        logger.error("generate-paper failed: %s (steps so far: %s)", res.get("message"), res.get("steps", []))
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

@router.get("/short-notes/{question_no}")
async def get_short_notes(question_no: str):
    """Generate short notes for a specific question using RAG from lecture slides."""
    from app.agents.researcher import ContentResearcher
    import json
    
    # Load the paper JSON to get question text
    json_path = os.path.join(str(OUTPUTS_DIR), "model_papers", "agentic_model_paper.json")
    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Paper not found")
    
    with open(json_path, "r", encoding="utf-8") as f:
        paper_data = json.load(f)
    
    # Find the question
    question = None
    for q in paper_data.get("questions", []):
        if q.get("question_no") == question_no.upper():
            question = q
            break
    
    if not question:
        raise HTTPException(status_code=404, detail=f"Question {question_no} not found")
    
    # Build query from question text and subquestions
    query_parts = [question.get("text", "")]
    if question.get("subquestions"):
        for sq in question.get("subquestions", []):
            query_parts.append(sq.get("text", ""))
    
    query = " ".join(query_parts)[:1000]  # Limit query length
    
    # Use ContentResearcher to get relevant content
    researcher = ContentResearcher(config={"top_k": 8})  # Get more chunks for better context
    
    try:
        # Retrieve relevant lecture content
        raw_notes = await researcher.run({"query": query})
        
        if not raw_notes or len(raw_notes.strip()) == 0:
            raise HTTPException(
                status_code=503, 
                detail="No relevant lecture content found. Please ensure lecture slides are uploaded and indexed."
            )
        
        # Generate formatted short notes using LLM
        from app.core.llm_factory import get_llm_client
        from app.core.config import settings
        
        llm_client = get_llm_client()
        
        subquestions_text = ""
        if question.get("subquestions"):
            subquestions_text = "\n".join([
                f"- {sq.get('label', '')}) {sq.get('text', '')}" 
                for sq in question.get("subquestions", [])
            ])
        
        prompt = f"""Given the following exam question and relevant lecture slide content, generate concise short notes that align with the curriculum.

**Exam Question ({question_no}):**
{question.get("text", "")}

**Subquestions:**
{subquestions_text}

**Relevant Lecture Content:**
{raw_notes[:6000]}

**Instructions:**
Generate short notes that:
1. Provide key definitions, concepts, and examples directly related to the exam question
2. Are concise and focused on high-priority topics
3. Include important formulas, rules, or procedures if applicable
4. Reflect the actual content from the lecture slides
5. Are organized in clear sections (Key Concepts, Definitions, Examples, etc.)

Format the output as markdown with clear headings and bullet points."""

        response = llm_client.chat.completions.create(
            model=settings.OPENAI_MODEL or "gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert educational assistant that creates concise, curriculum-aligned study notes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.4
        )
        
        short_notes = response.choices[0].message.content
        
        return {
            "question_no": question_no,
            "question_text": question.get("text", ""),
            "short_notes": short_notes,
            "source": "RAG from lecture slides"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating short notes: {str(e)}")