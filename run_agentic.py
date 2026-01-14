import asyncio
import os
import sys
from pathlib import Path

# Handle Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Set up project root and Python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT / "backend"))

async def run_now():
    print("Starting Standalone Agentic Generation...")
    
    # Import inside function to ensure paths are set
    from app.agents.orchestrator import AgentOrchestrator
    from app.core.db import db
    
    try:
        # Initialize DB
        db.connect()
        
        # Run Orchestrator
        orchestrator = AgentOrchestrator()
        await orchestrator.run_pipeline()
        
        print("\n[OK] Standalone Generation Finished!")
    except Exception as e:
        print(f"\n[ERROR] Error during generation: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_now())
