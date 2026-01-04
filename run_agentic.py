import asyncio
import os
import sys
from pathlib import Path

# Set up project root and Python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT / "backend"))

async def run_now():
    print("🚀 Starting Standalone Agentic Generation...")
    
    # Import inside function to ensure paths are set
    from app.agents.orchestrator import AgentOrchestrator
    from app.core.db import db
    
    try:
        # Initialize DB
        await db.connect_to_mongo()
        
        # Run Orchestrator
        orchestrator = AgentOrchestrator()
        await orchestrator.run_pipeline()
        
        print("\n✅ Standalone Generation Finished!")
    except Exception as e:
        print(f"\n❌ Error during generation: {e}")
    finally:
        await db.close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(run_now())
