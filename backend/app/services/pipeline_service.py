# Service to orchestrate the pipeline

from app.services.pastpaper_service import process_past_paper
from app.services.slides_service import process_lecture_slides
from app.services.structure_service import generate_exam_structure
from app.services.generation_service import generate_model_paper

def run_pipeline(file_type: str, file_path: str) -> Dict[str, Any]:
    steps: List[str] = []

    if file_type == "past_paper":
        steps.append("Processing past paper...")
        pp_result = process_past_paper(file_path)
        steps.append("Past paper processed successfully.")

        steps.append("Generating exam structure (from past papers)...")
        structure_result = generate_exam_structure()
        steps.append("Structure generated successfully.")

    elif file_type == "slides":
        steps.append("Processing lecture slides...")
        slides_result = process_lecture_slides(file_path)
        steps.append("Lecture slides processed successfully.")

        steps.append("Generating exam structure (from artifacts)...")
        structure_result = generate_exam_structure()
        steps.append("Structure generated successfully.")

    else:
        raise ValueError(f"Unsupported file_type: {file_type}")

    steps.append("Generating model paper...")
    model_result = generate_model_paper()
    steps.append("Model paper generated successfully.")

    return {
        "status": "success",
        "steps": steps,
        "past_paper": pp_result if file_type == "past_paper" else None,
        "slides": slides_result if file_type == "slides" else None,
        "structure": structure_result,
        "model_paper": model_result,
    }