# Service to orchestrate the pipeline (NO file processing)

from typing import Dict, Any, List
from app.services.structure_service import generate_exam_structure
from app.services.generation_service import generate_model_paper


def run_pipeline(source: str) -> Dict[str, Any]:
    """
    source: "past_paper" | "slides" | "all"
    Assumes artifacts already exist.
    """

    steps: List[str] = []

    # STEP 1 — Generate exam structure
    steps.append(f"Generating exam structure using source = {source} ...")
    structure_result = generate_exam_structure(source=source)
    steps.append("Exam structure generated successfully.")

    # STEP 2 — Generate model paper
    steps.append("Generating model paper using existing artifacts...")
    model_result = generate_model_paper()
    steps.append("Model paper generated successfully.")

    return {
        "status": "success",
        "source": source,
        "steps": steps,
        "structure": structure_result,
        "model_paper": model_result,
    }
