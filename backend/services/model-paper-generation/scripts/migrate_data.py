import asyncio
import json
import glob, os, sys
from pathlib import Path

# Add service root to path
_service_root = str(Path(__file__).resolve().parents[1])
if _service_root not in sys.path:
    sys.path.insert(0, _service_root)

from app.core.db import db
from app.core.paths import ARTIFACTS_DIR, OUTPUTS_DIR

async def migrate_templates():
    """Migrate template_questions.json and canonical_templates.json."""
    database = db.get_db()
    
    # 1. Raw Templates
    tpl_path = ARTIFACTS_DIR / "template_questions.json"
    if tpl_path.exists():
        data = json.loads(tpl_path.read_text(encoding="utf-8"))
        if data:
            print(f"Migrating {len(data)} raw templates...")
            await database.templates.delete_many({})  # Clear old
            await database.templates.insert_many(data)
            print("Templates migrated.")

    # 2. Canonical Templates
    canon_path = ARTIFACTS_DIR / "canonical_templates.json"
    if canon_path.exists():
        data = json.loads(canon_path.read_text(encoding="utf-8"))
        # Convert dict to list of documents with ID
        docs = []
        for key, val in data.items():
            val["position_id"] = key # e.g. "Q1"
            docs.append(val)
            
        if docs:
            print(f"Migrating {len(docs)} canonical templates...")
            await database.canonical_templates.delete_many({})
            await database.canonical_templates.insert_many(docs)
            print("Canonical templates migrated.")

async def migrate_papers():
    """Migrate generated papers from outputs directory."""
    database = db.get_db()
    
    paper_files = list(OUTPUTS_DIR.glob("model_papers/*.json"))
    for p_path in paper_files:
        if "checkpoint" in p_path.name:
            continue
            
        try:
            data = json.loads(p_path.read_text(encoding="utf-8"))
            # Check if exists
            exists = await database.papers.find_one({"generated_at": data.get("generated_at")})
            if not exists:
                print(f"🚀 Migrating paper: {p_path.name}")
                await database.papers.insert_one(data)
        except Exception as e:
            print(f"⚠️ Failed to migrate {p_path.name}: {e}")
            
    print("Papers migrated.")

async def main():
    print("--- STARTING MIGRATION ---")
    await migrate_templates()
    await migrate_papers()
    print("--- MIGRATION COMPLETE ---")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
