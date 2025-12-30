# Service to orchestrate the pipeline

from backend.app.services.pastpaper_service import process_past_paper
from backend.app.services.slides_service import process_slides
from backend.app.services.structure_service import generate_structure
from backend.app.services.generation_service import generate_model_paper

def run_pipeline(file_type, file_path):
    statuses = []

    if file_type == "past_paper":
        statuses.append("Processing past paper...")
        process_past_paper(file_path)
        statuses.append("Past paper processed successfully.")

        statuses.append("Generating structure from past paper...")
        generate_structure("past_paper")
        statuses.append("Structure generated successfully.")

    elif file_type == "slides":
        statuses.append("Processing lecture slides...")
        process_slides(file_path)
        statuses.append("Lecture slides processed successfully.")

        statuses.append("Generating structure from slides...")
        generate_structure("slides")
        statuses.append("Structure generated successfully.")

    statuses.append("Generating model paper...")
    result = generate_model_paper()
    statuses.append("Model paper generated successfully.")

    return {
        "status": "success",
        "steps": statuses,
        "outputs": result
    }