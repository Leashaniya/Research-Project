import asyncio
import os
import sys
from pathlib import Path

# Add backend to python path dynamically
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent # backend is the parent of scripts
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    # If for some reason we are in a different structure
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
