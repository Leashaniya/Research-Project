import asyncio
from app.agents.orchestrator import AgentOrchestrator
import os

# Mock OpenAI for testing if keys are missing
# For real test, ensure .env has keys.
# This script tries to run the real thing, but if it fails, it prints why.

async def verify_agents():
    print("Initializing Agent Orchestrator...")
    try:
        orchestrator = AgentOrchestrator()
        
        # We can mock the individual agents run methods to test flow if we don't want to burn tokens
        # But for now let's try to run it. 
        # CAUTION: This will try to use OpenAI API.
        
        if not os.environ.get("OPENAI_API_KEY"):
            print("⚠️ HEADS UP: OPENAI_API_KEY not found in env. Agents will likely fail.")
        
        print("Running pipeline (dry-run style if possible)...")
        # To avoid full execution, we could mock the blueprint or limit slots.
        # But let's just run it. The user asked for it.
        
        result = await orchestrator.run_pipeline()
        print("Pipeline finished!")
        print(result)

    except Exception as e:
        print(f"❌ Verification failed (Expected if no API Key): {e}")

if __name__ == "__main__":
    asyncio.run(verify_agents())
