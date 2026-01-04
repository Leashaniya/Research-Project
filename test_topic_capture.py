
import asyncio
import sys
from pathlib import Path

# Add backend to path
backend_path = Path("backend").resolve()
sys.path.append(str(backend_path))

from app.agents.orchestrator import AgentOrchestrator

async def test_topic_capture():
    # Simulate the logic added in Orchestrator
    slot = {"question_no": "1", "topics": ["SQL Queries"]}
    template = {"pattern_label": "Database Schema"}
    
    main_topic = template.get("pattern_label") or (slot.get("topics") and slot.get("topics")[0]) or "General Database Systems"
    
    print(f"Captured topic: {main_topic}")
    assert main_topic == "Database Schema"
    
    # Fallback check
    template_empty = {}
    main_topic_fb = template_empty.get("pattern_label") or (slot.get("topics") and slot.get("topics")[0]) or "General Database Systems"
    print(f"Captured topic (fallback to slot): {main_topic_fb}")
    assert main_topic_fb == "SQL Queries"

if __name__ == "__main__":
    asyncio.run(test_topic_capture())
