import asyncio
import os
import sys
from pathlib import Path

# Add backend to python path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.agents.orchestrator import main as agentic_main

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    print("🚀 Starting Agentic Pipeline...")
    try:
        asyncio.run(agentic_main())
    except KeyboardInterrupt:
        print("\n🛑 Pipeline stopped by user.")
    except Exception as e:
        print(f"\n❌ Pipeline failed: {e}")
