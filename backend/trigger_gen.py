import asyncio
import sys
import os

# Add the current directory to sys.path so we can import 'app'
sys.path.append(os.getcwd())

from app.agents.orchestrator import main
from app.core.db import db

async def run_standalone():
    db.connect()
    try:
        await main()
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_standalone())
