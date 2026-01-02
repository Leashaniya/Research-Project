import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.core.db import db

async def verify_data():
    database = db.get_db()
    
    # Check collections
    templates_count = await database.templates.count_documents({})
    canonical_count = await database.canonical_templates.count_documents({})
    papers_count = await database.papers.count_documents({})
    
    print("\n📊 MongoDB Data Verification:")
    print(f"   - Templates: {templates_count}")
    print(f"   - Canonical Templates: {canonical_count}")
    print(f"   - Generated Papers: {papers_count}")
    
    if templates_count > 0 and canonical_count > 0:
        print("\n✅ Data looks healthy!")
    else:
        print("\n⚠️ Warning: Some collections are empty.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(verify_data())
