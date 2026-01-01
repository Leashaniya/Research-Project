from typing import Dict, Any, List
from pathlib import Path
import asyncio

from scripts.pastpaper_extract import main_full_run
from scripts.lectureslide_extract import main as slides_main
from scripts.structure_topics_template import main as structure_main
from app.agents.orchestrator import main as agentic_main

from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR


def _pdfs_in(folder: Path):
    return list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))


def run_full_pipeline() -> Dict[str, Any]:
    steps: List[str] = []

    pp_dir = Path(PAST_PAPERS_DIR)
    sl_dir = Path(SLIDES_DIR)

    print("PIPELINE: past papers dir =", pp_dir)
    print("PIPELINE: slides dir      =", sl_dir)

    pp_pdfs = _pdfs_in(pp_dir) if pp_dir.exists() else []
    sl_pdfs = _pdfs_in(sl_dir) if sl_dir.exists() else []

    print("PIPELINE: past papers PDFs =", [p.name for p in pp_pdfs])
    print("PIPELINE: slides PDFs      =", [p.name for p in sl_pdfs])

    try:
        # Step 1
        if pp_pdfs:
            steps.append("Processing past papers...")
            main_full_run()
            steps.append("Past papers processed.")
        else:
            steps.append("No past papers found. Skipping past paper processing.")

        # Step 2
        if sl_pdfs:
            steps.append("Processing lecture slides...")
            slides_main()
            steps.append("Lecture slides processed.")
        else:
            steps.append("No lecture slides found. Skipping lecture slide processing.")

        # Step 3
        steps.append("Generating exam structure & templates...")
        structure_main()
        steps.append("Exam structure & templates generated.")

        # Step 4
        steps.append("Generating model paper (Agentic Mode)...")
        # generate_main() # OLD SCRIPT
        loop = asyncio.get_event_loop()
        # Since run_full_pipeline is not async defined in the original file, we might need a wrapper or run_until_complete
        # However, FastAPI handles async. Let's assume we can run it synchronously if needed or update the service sig.
        # Ideally, `run_full_pipeline` should be `async def`. But checking file... it is `def`.
        # So we use a runner.
        loop.run_until_complete(agentic_main())
        
        steps.append("Model paper generated (Agentic).")
        
        return {"status": "success", "steps": steps}

    except Exception as e:
        print(f"PIPELINE ERROR: {e}")
        steps.append(f"Error encountered: {str(e)}")
        steps.append("Falling back to MOCK generation for presentation.")
        
        # Mock Response
        mock_paper = {
            "generated_at": "MOCK_TIME",
            "model": "MOCK_MODEL",
            "total_marks": 100,
            "questions": [
                {
                    "question_no": "Q1",
                    "marks": 25,
                    "pattern_label": "THEORY",
                    "question_text": "Explain the concept of Artificial Intelligence in the context of modern web applications. (MOCK QUESTION)"
                },
                {
                    "question_no": "Q2",
                    "marks": 25,
                    "pattern_label": "PRACTICAL",
                    "question_text": "Write a Python function to demonstrate a simple neural network forward pass. (MOCK QUESTION)"
                },
                {
                    "question_no": "Q3",
                    "marks": 25,
                    "pattern_label": "ANALYSIS",
                    "question_text": "Analyze the impact of Large Language Models on software engineering practices. (MOCK QUESTION)"
                },
                {
                    "question_no": "Q4",
                    "marks": 25,
                    "pattern_label": "DESIGN",
                    "question_text": "Design a system architecture for a real-time chat application using WebSocket. (MOCK QUESTION)"
                }
            ]
        }
        
        return {
            "status": "partial_success", 
            "steps": steps, 
            "message": "Pipeline failed (likely due to missing API keys/data), returning MOCK data for demo.",
            "data": mock_paper
        }
