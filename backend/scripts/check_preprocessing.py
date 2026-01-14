"""
Check if all preprocessing outputs exist and are valid.
"""
import sys
import json
from pathlib import Path

# Handle Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add backend to path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    sys.path.append(str(project_root / "backend"))

def check_preprocessing():
    """Check if all required preprocessing outputs exist."""
    print("="*70)
    print("PREPROCESSING STATUS CHECK")
    print("="*70)
    
    project_root = Path(__file__).resolve().parents[2]
    
    # Check 1: Blueprint
    blueprint_path = project_root / "data" / "artifacts" / "exam_blueprint_template.json"
    print(f"\n1. Blueprint:")
    print(f"   Path: {blueprint_path}")
    if blueprint_path.exists():
        try:
            bp_data = json.loads(blueprint_path.read_text(encoding="utf-8"))
            slots = bp_data.get("question_slots", [])
            total_marks = sum(s.get("target_marks", 0) for s in slots)
            canonical_total = bp_data.get("canonical_total_marks", 0)
            print(f"   [OK] Exists")
            print(f"   - Slots: {len(slots)}")
            print(f"   - Total marks (sum): {total_marks}")
            print(f"   - Canonical total: {canonical_total}")
            if total_marks == canonical_total:
                print(f"   - [OK] Marks match: {total_marks} == {canonical_total}")
            else:
                print(f"   - [WARN] Marks mismatch: {total_marks} != {canonical_total} (will be reconciled)")
        except Exception as e:
            print(f"   [ERROR] Invalid JSON: {e}")
    else:
        print(f"   [MISSING] Blueprint not found")
        print(f"   -> Run: python backend/scripts/structure_topics_template.py")
    
    # Check 2: Canonical Templates
    canonical_path = project_root / "data" / "artifacts" / "canonical_templates.json"
    print(f"\n2. Canonical Templates:")
    print(f"   Path: {canonical_path}")
    if canonical_path.exists():
        try:
            ct_data = json.loads(canonical_path.read_text(encoding="utf-8"))
            if isinstance(ct_data, dict):
                count = len(ct_data)
            elif isinstance(ct_data, list):
                count = len(ct_data)
            else:
                count = 0
            print(f"   [OK] Exists")
            print(f"   - Templates: {count}")
        except Exception as e:
            print(f"   [ERROR] Invalid JSON: {e}")
    else:
        print(f"   [MISSING] Canonical templates not found")
        print(f"   -> Run: python backend/scripts/template_analyzer.py")
    
    # Check 3: Past Papers (at least one should exist)
    past_papers_dir = project_root / "data" / "text_extraction_hybrid"
    print(f"\n3. Past Papers:")
    print(f"   Path: {past_papers_dir}")
    if past_papers_dir.exists():
        paper_dirs = [d for d in past_papers_dir.iterdir() if d.is_dir()]
        print(f"   [OK] Exists")
        print(f"   - Papers found: {len(paper_dirs)}")
        if len(paper_dirs) == 0:
            print(f"   - [WARN] No past papers extracted")
            print(f"   -> Run: python backend/scripts/pastpaper_extract.py")
    else:
        print(f"   [MISSING] Past papers directory not found")
        print(f"   -> Run: python backend/scripts/pastpaper_extract.py")
    
    # Check 4: Lecture Slides (optional but recommended)
    slides_dir = project_root / "data" / "slides_embeddings"
    print(f"\n4. Lecture Slides (Optional):")
    print(f"   Path: {slides_dir}")
    if slides_dir.exists():
        faiss_files = list(slides_dir.glob("*.index"))
        print(f"   [OK] Exists")
        print(f"   - FAISS indices: {len(faiss_files)}")
    else:
        print(f"   [INFO] Not found (optional, but recommended)")
        print(f"   -> Run: python backend/scripts/lectureslide_extract.py")
    
    # Check 5: MongoDB (check if templates are synced)
    print(f"\n5. MongoDB Sync:")
    try:
        import asyncio
        from app.core.db import db
        
        async def check_mongo():
            db.connect()
            db_instance = db.get_db()
            templates_count = await db_instance.templates.count_documents({})
            canonical_count = await db_instance.canonical_templates.count_documents({})
            db.close()
            return templates_count, canonical_count
        
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        templates_count, canonical_count = asyncio.run(check_mongo())
        print(f"   [OK] Connected")
        print(f"   - Templates in DB: {templates_count}")
        print(f"   - Canonical templates in DB: {canonical_count}")
        if templates_count == 0:
            print(f"   - [WARN] No templates in MongoDB")
            print(f"   -> Run: python backend/scripts/migrate_data.py")
    except Exception as e:
        print(f"   [ERROR] MongoDB connection failed: {e}")
        print(f"   -> Check MongoDB connection and run: python backend/scripts/migrate_data.py")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    # Final check
    all_ok = (
        blueprint_path.exists() and
        canonical_path.exists() and
        past_papers_dir.exists() and
        len([d for d in past_papers_dir.iterdir() if d.is_dir()]) > 0
    )
    
    if all_ok:
        print("[OK] All required preprocessing outputs exist")
        print("You can proceed with agentic generation.")
    else:
        print("[WARN] Some preprocessing outputs are missing")
        print("Run preprocessing steps before agentic generation.")
    
    return all_ok

if __name__ == "__main__":
    success = check_preprocessing()
    sys.exit(0 if success else 1)

