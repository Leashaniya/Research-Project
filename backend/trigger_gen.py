import asyncio
import sys
import os

# Add the current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.agents.orchestrator import main

if __name__ == "__main__":
    asyncio.run(main())
