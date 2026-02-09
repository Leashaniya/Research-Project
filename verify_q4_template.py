"""
Verify Q4 Template Selection
Check if Q4 will use the correct RELATIONAL_ALGEBRA template from past papers
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from backend.app.core.db import db
import json

async def verify_q4_template():
    """Check Q4 template selection"""
    print("=" * 60)
    print("VERIFYING Q4 TEMPLATE SELECTION")
    print("=" * 60)
    
    database = db.get_db()
    
    # 1. Check canonical template
    print("\n1. CANONICAL TEMPLATE (from canonical_templates.json):")
    print("-" * 60)
    canonical = await database.canonical_templates.find_one({"position_id": "Q4"})
    if canonical:
        print(f"[OK] Found canonical template for Q4")
        print(f"   Pattern Label: {canonical.get('pattern_label')}")
        print(f"   Source Paper: {canonical.get('source_paper')}")
        print(f"   Total Marks: {canonical.get('total_marks')}")
        print(f"   Subquestion Count: {canonical.get('subquestion_count')}")
        print(f"   Structure:")
        for idx, sq in enumerate(canonical.get('subquestion_structure', [])[:3], 1):
            print(f"      {idx}. [{sq.get('marks')} marks] {sq.get('text', '')[:60]}...")
        if len(canonical.get('subquestion_structure', [])) > 3:
            print(f"      ... ({len(canonical.get('subquestion_structure', [])) - 3} more)")
    else:
        print("[ERROR] No canonical template found for Q4")
    
    # 2. Check templates in MongoDB
    print("\n2. TEMPLATES IN MONGODB (for RELATIONAL_ALGEBRA):")
    print("-" * 60)
    templates = await database.templates.find({
        "pattern_label": "RELATIONAL_ALGEBRA",
        "marks": {"$gte": 35, "$lte": 45}  # Around 40 marks
    }).to_list(length=5)
    
    if templates:
        print(f"[OK] Found {len(templates)} RELATIONAL_ALGEBRA templates (35-45 marks)")
        for idx, t in enumerate(templates[:3], 1):
            print(f"   Template {idx}:")
            print(f"      Marks: {t.get('marks')}")
            print(f"      Source: {t.get('pdf_stem', 'Unknown')}")
            print(f"      Text preview: {t.get('full_text', '')[:80]}...")
    else:
        print("[WARN] No RELATIONAL_ALGEBRA templates found in MongoDB (35-45 marks)")
    
    # 3. Check templates for Q4 position
    print("\n3. TEMPLATES FOR Q4 POSITION:")
    print("-" * 60)
    q4_templates = await database.templates.find({
        "question_id": "4",
        "full_text": {"$exists": True, "$ne": ""}
    }).to_list(length=5)
    
    if q4_templates:
        print(f"[OK] Found {len(q4_templates)} templates with question_id='4'")
        for idx, t in enumerate(q4_templates[:3], 1):
            print(f"   Template {idx}:")
            print(f"      Pattern Label: {t.get('pattern_label')}")
            print(f"      Marks: {t.get('marks')}")
            print(f"      Source: {t.get('pdf_stem', 'Unknown')}")
    else:
        print("[WARN] No templates found with question_id='4'")
    
    # 4. Check blueprint
    print("\n4. BLUEPRINT EXPECTATIONS:")
    print("-" * 60)
    blueprint_path = Path("data/artifacts/exam_blueprint_template.json")
    if blueprint_path.exists():
        blueprint = json.loads(blueprint_path.read_text())
        q4_slot = next((s for s in blueprint.get("question_slots", []) if s.get("slot_id") == "Q4"), None)
        if q4_slot:
            print(f"[OK] Q4 Blueprint Slot:")
            print(f"   Target Marks: {q4_slot.get('target_marks')}")
            print(f"   Typical Subquestions: {q4_slot.get('typical_num_subquestions')}")
            print(f"   Topics: {q4_slot.get('topics', [])}")
            print(f"   Forced Topic: {q4_slot.get('forced_topic', False)}")
    
    # 5. Summary
    print("\n" + "=" * 60)
    print("SUMMARY:")
    print("=" * 60)
    if canonical and canonical.get('pattern_label') == 'RELATIONAL_ALGEBRA':
        print("[OK] Q4 will use RELATIONAL_ALGEBRA template from canonical_templates.json")
        print(f"   Source: {canonical.get('source_paper')} paper")
        print(f"   Structure: {canonical.get('subquestion_count')} subquestions")
        print(f"   Expected format: Relational algebra queries + tuple calculus")
    else:
        print("[WARN] WARNING: Q4 canonical template may not be RELATIONAL_ALGEBRA")
    
    if templates:
        print(f"[OK] Found {len(templates)} RELATIONAL_ALGEBRA templates in MongoDB")
    else:
        print("[WARN] WARNING: No RELATIONAL_ALGEBRA templates found in MongoDB")
        print("   This may cause fallback to GENERAL_THEORY")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(verify_q4_template())
