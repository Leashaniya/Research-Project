from typing import Dict, Any, List
from pathlib import Path

from scripts.pastpaper_extract import main_full_run
from scripts.lectureslide_extract import main as slides_main
from scripts.structure_topics_template import main as structure_main
from scripts.generate_model_paper_openai import main as generate_main

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
    steps.append("Generating model paper...")
    generate_main()
    steps.append("Model paper generated.")

    return {"status": "success", "steps": steps}
