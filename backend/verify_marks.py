import json
from pathlib import Path
from app.core.paths import DATA_DIR, ARTIFACTS_DIR

def check_marks():
    print("--- AUDIT: CHECKING EXAM MARKS ---\n")
    
    # 1. Check the Generated Blueprint (The target for new papers)
    blueprint_path = ARTIFACTS_DIR / "exam_blueprint_template.json"
    if blueprint_path.exists():
        bp = json.loads(blueprint_path.read_text(encoding="utf-8"))
        slots = bp.get("question_slots", [])
        total = sum(s.get("target_marks", 0) for s in slots)
        print(f"📘 BLUEPRINT TEMPLATE ({blueprint_path.name})")
        print(f"   Target Total Marks: {total}")
        if total == 100:
            print("   ✅ Status: CORRECT (100 Marks)")
        else:
            print(f"   ⚠️ Status: MISMATCH (Expected 100, got {total})")
    else:
        print("❌ Blueprint artifact not found.")

    print("\n------------------------------------------------\n")

    # 2. Check the Source Past Papers (Analysis)
    print("📂 ANALYZING SOURCE PAST PAPERS:")
    extraction_dir = DATA_DIR / "text_extraction_hybrid"
    
    if not extraction_dir.exists():
        print("   No extraction directory found.")
        return

    for folder in sorted(extraction_dir.iterdir()):
        if not folder.is_dir(): 
            continue
            
        json_path = folder / "blueprint_with_subquestions.json"
        if not json_path.exists():
            json_path = folder / "blueprint.json"
        
        if json_path.exists():
            try:
                data = json.loads(json_path.read_text(encoding="utf-8"))
                paper_total = 0
                for q in data:
                    # Logic matches structure_topics_template.py
                    m = q.get("marks")
                    if m is None:
                        # try summing subquestions
                        subs = q.get("subquestions", [])
                        m = sum(int(s.get("marks", 0) or 0) for s in subs)
                    else:
                        m = int(m)
                    paper_total += m
                
                status = "✅" if paper_total == 100 else "⚠️"
                print(f"   {status} {folder.name}: {paper_total} Marks")
            except Exception as e:
                print(f"   ❌ {folder.name}: Error reading marks ({e})")

if __name__ == "__main__":
    check_marks()
