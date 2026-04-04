import logging
import re
from typing import Optional, Literal, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services import pipeline_service
from app.services.paper_a_dynamic_slots import compute_paper_a_num_slots_from_recent_papers
from app.core.paths import OUTPUTS_DIR, PAST_PAPERS_DIR
import os
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter()


class GeneratePaperRequest(BaseModel):
  """User-configurable parameters for model paper generation."""
  num_slots: Optional[int] = None
  selected_papers: Optional[List[dict]] = None
  semester_bias: Optional[Literal["both", "sem1", "sem2"]] = None
  coverage_strategy: Optional[Literal["trend", "max_variety", "focus_selected"]] = None
  last_n_years: Optional[int] = None
  knowledge_weighting: Optional[Literal["past_papers", "balanced", "lecture_slides"]] = None
  num_versions: Optional[int] = None
  # Paper B: output questions only — no marks in JSON/PDF; skip strict marks validation
  questions_only: Optional[bool] = None
  # Paper B: when true (default for POST /generate-paper), topic/trend from lecture MiniLM+KMeans; set false to use past-paper trends
  lecture_based_topics: Optional[bool] = None

@router.post("/process-files")
async def process_files():
    """Step 1: Process uploads, extract text, and build templates."""
    res = await pipeline_service.process_uploaded_files()
    if res["status"] == "error":
        logger.error("process-files failed: %s", res.get("message"), exc_info=True)
        raise HTTPException(status_code=500, detail=res["message"])
    return res

@router.post("/generate-paper-a")
async def generate_paper_a():
    """
    Paper A: Standard generation
    - num_slots: MODE of per-paper question counts from the last 6 calendar years (cached blueprints);
      multimodal tie → smallest mode; clamped 1–8; fallback 4 if no data.
    - Uses ALL uploaded past papers for trend/topic computation.
    - Ignores any user-provided custom generation options.
    """
    def _parse_file_to_selection_item(filename: str) -> dict:
        name = str(filename or "")
        m = re.search(r"(20\d{2})", name)
        year = int(m.group(1)) if m else None
        sem = "sem2" if re.search(r"\bII\b", name, re.IGNORECASE) else "sem1"
        return {"year": year, "sem": sem, "file": name}

    pp_dir = Path(PAST_PAPERS_DIR)
    all_pdfs = []
    if pp_dir.exists():
        all_pdfs = sorted([p.name for p in pp_dir.glob("*.pdf")] + [p.name for p in pp_dir.glob("*.PDF")])

    num_slots, slots_meta = compute_paper_a_num_slots_from_recent_papers()

    options = {
        "num_slots": num_slots,
        "semester_bias": "both",
        "selected_papers": [_parse_file_to_selection_item(f) for f in all_pdfs],
    }

    res = await pipeline_service.run_full_pipeline(options=options)
    if res["status"] == "success":
        res["paper_a_slot_inference"] = slots_meta
    if res["status"] == "error":
        msg = res.get("message") or "Pipeline failed"
        detail = str(msg) if msg else "Pipeline failed"
        logger.error("generate-paper-a failed: %s (steps so far: %s)", detail, res.get("steps", []), exc_info=True)
        raise HTTPException(status_code=500, detail=detail)
    return res

@router.post("/generate-paper")
async def generate_paper(params: GeneratePaperRequest | None = None):
    """Runs the COMPLETE pipeline: Extraction -> Blueprinting -> AI Generation."""
    options = params.dict(exclude_none=True) if params else {}
    # Paper B default: mine topics from lecture slide corpus (not selected past papers)
    if options.get("lecture_based_topics") is None:
        options["lecture_based_topics"] = True
    res = await pipeline_service.run_full_pipeline(options=options)
    if res["status"] == "error":
        msg = res.get("message") or "Pipeline failed"
        detail = str(msg) if msg else "Pipeline failed"
        logger.error("generate-paper failed: %s (steps so far: %s)", detail, res.get("steps", []), exc_info=True)
        raise HTTPException(status_code=500, detail=detail)
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
    """Download the latest generated PDF paper. Always regenerates from JSON so the PDF matches the preview."""
    import json
    from app.services.pdf_service import PDFService

    json_path = os.path.join(str(OUTPUTS_DIR), "model_papers", "agentic_model_paper.json")
    path = os.path.join(str(OUTPUTS_DIR), "model_papers", "agentic_model_paper.pdf")

    if not os.path.exists(json_path):
        raise HTTPException(status_code=404, detail="Paper not found. Please generate the paper first.")

    with open(json_path, "r", encoding="utf-8") as f:
        paper_data = json.load(f)

    try:
        pdf_service = PDFService()
        pdf_service.generate_pdf(paper_data, path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate PDF: {str(e)}")

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