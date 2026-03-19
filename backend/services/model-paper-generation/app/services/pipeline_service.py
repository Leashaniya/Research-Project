from typing import Dict, Any, List
from pathlib import Path
import asyncio
import logging

from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR

logger = logging.getLogger(__name__)


def _pdfs_in(folder: Path):
    return list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))


async def process_uploaded_files() -> Dict[str, Any]:
    """Runs OCR, extraction, and template generation for all uploaded files."""
    steps: List[str] = []
    pp_dir = Path(PAST_PAPERS_DIR)
    sl_dir = Path(SLIDES_DIR)

    pp_pdfs = _pdfs_in(pp_dir) if pp_dir.exists() else []
    sl_pdfs = _pdfs_in(sl_dir) if sl_dir.exists() else []

    try:
        if pp_pdfs:
            from scripts.pastpaper_extract import main_full_run
            steps.append(f"Processing {len(pp_pdfs)} past papers...")
            await asyncio.to_thread(main_full_run)
            steps.append("Past papers processed.")
        
        if sl_pdfs:
            from scripts.lectureslide_extract import main as slides_main
            steps.append(f"Processing {len(sl_pdfs)} lecture slides...")
            await asyncio.to_thread(slides_main)
            steps.append("Lecture slides processed.")
        
        steps.append("Generating exam structure and topic clusters...")
        from scripts.structure_topics_template import main as structure_main
        await asyncio.to_thread(structure_main)
        
        steps.append("Analyzing question patterns and selecting canonical templates...")
        from scripts.template_analyzer import analyze_templates
        await asyncio.to_thread(analyze_templates)
        
        steps.append("Syncing templates to brain (database)...")
        try:
            from scripts.migrate_data import main as migrate_main
            await migrate_main() # migrate_main is already async
            steps.append("Exam structure and templates generated & synced.")
        except Exception as mig_err:
            logger.warning("MongoDB migration failed (non-fatal): %s", mig_err)
            steps.append(f"⚠️ Database sync skipped (non-fatal): {mig_err}")
            steps.append("Continuing with local artifacts...")

        return {"status": "success", "steps": steps}
    except Exception as e:
        logger.exception("process_uploaded_files failed: %s", e)
        return {"status": "error", "message": str(e), "steps": steps}

async def run_agentic_generation(options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Runs the AI agents to generate the final model paper."""
    steps: List[str] = []
    try:
        steps.append("Waking up AI agents...")
        from app.agents.orchestrator import main as agentic_main

        # TODO: in future, thread user-specified options into the agentic pipeline.
        _ = options or {}

        paper = await agentic_main()
        steps.append("Agentic generation complete.")
        
        return {"status": "success", "steps": steps, "paper": paper}
    except Exception as e:
        logger.exception("run_agentic_generation failed: %s", e)
        return {"status": "error", "message": str(e), "steps": steps}

async def run_full_pipeline(options: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Legacy endpoint for total automation."""
    res1 = await process_uploaded_files()
    if res1["status"] == "error": return res1
    res2 = await run_agentic_generation(options=options)
    res2["steps"] = res1["steps"] + res2["steps"]
    return res2
