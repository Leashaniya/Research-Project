"""
Run Full Pipeline: Preprocessing + Agentic Generation
Runs all preprocessing steps and then generates the model paper
"""
import asyncio
import os
import sys
from pathlib import Path

# Handle Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Set up project root and Python path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

async def run_preprocessing():
    """Run all preprocessing steps"""
    print("\n" + "="*70)
    print("STEP 1: PREPROCESSING")
    print("="*70 + "\n")
    
    from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR
    
    pp_dir = Path(PAST_PAPERS_DIR)
    sl_dir = Path(SLIDES_DIR)
    
    def _pdfs_in(folder: Path):
        return list(folder.glob("*.pdf")) + list(folder.glob("*.PDF"))
    
    pp_pdfs = _pdfs_in(pp_dir) if pp_dir.exists() else []
    sl_pdfs = _pdfs_in(sl_dir) if sl_dir.exists() else []
    
    try:
        # Skip past paper and lecture slide processing (already done)
        print("[SKIP] Past paper extraction (already processed)\n")
        print("[SKIP] Lecture slide extraction (already processed)\n")
        
        # 1. Blueprint Generation
        print("[1/3] Generating exam structure and topic clusters...")
        from scripts.structure_topics_template import main as structure_main
        await asyncio.to_thread(structure_main)
        print("[OK] Exam structure and topic clusters generated.\n")
        
        # 2. Template Analysis
        print("[2/3] Analyzing question patterns and selecting canonical templates...")
        from scripts.template_analyzer import analyze_templates
        await asyncio.to_thread(analyze_templates)
        print("[OK] Canonical templates selected.\n")
        
        # 3. Database Migration
        print("[3/3] Syncing templates to MongoDB...")
        from scripts.migrate_data import main as migrate_main
        await migrate_main()  # migrate_main is already async
        print("[OK] Templates synced to MongoDB.\n")
        
        print("="*70)
        print("PREPROCESSING COMPLETE")
        print("="*70 + "\n")
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Preprocessing failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def run_agentic_generation():
    """Run agentic pipeline to generate model paper"""
    print("\n" + "="*70)
    print("STEP 2: AGENTIC GENERATION")
    print("="*70 + "\n")
    
    from app.agents.orchestrator import AgentOrchestrator
    from app.core.db import db
    
    try:
        # Initialize DB
        db.connect()
        
        # Run Orchestrator
        orchestrator = AgentOrchestrator()
        await orchestrator.run_pipeline()
        
        print("\n" + "="*70)
        print("AGENTIC GENERATION COMPLETE")
        print("="*70 + "\n")
        return True
    except Exception as e:
        print(f"\n[ERROR] Agentic generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

async def main():
    """Run full pipeline: preprocessing + agentic generation"""
    print("\n" + "="*70)
    print("FULL PIPELINE: PREPROCESSING + AGENTIC GENERATION")
    print("="*70)
    
    # Step 1: Preprocessing
    preprocessing_success = await run_preprocessing()
    if not preprocessing_success:
        print("\n[ERROR] Preprocessing failed. Aborting agentic generation.")
        return
    
    # Step 2: Agentic Generation
    generation_success = await run_agentic_generation()
    
    if generation_success:
        print("\n" + "="*70)
        print("FULL PIPELINE COMPLETE")
        print("="*70)
        print("\nGenerated files:")
        print("  - JSON: data/outputs/model_papers/agentic_model_paper.json")
        print("  - PDF: data/outputs/model_papers/agentic_model_paper.pdf")
    else:
        print("\n[ERROR] Pipeline completed with errors.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
