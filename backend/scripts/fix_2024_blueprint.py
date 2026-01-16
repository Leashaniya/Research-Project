
import sys
import json
from pathlib import Path

# Add backend to path (backend/)
sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.structure_service import analyze_document_structure

def fix_2024_ii_blueprint():
    # Paths
    project_root = Path(__file__).resolve().parents[2]
    data_root = project_root / "data" / "text_extraction_hybrid" / "2024 II"
    cleaned_doc_path = data_root / "cleaned_document.txt"
    blueprint_path = data_root / "blueprint_with_subquestions.json"

    if not cleaned_doc_path.exists():
        print(f"Error: cleaned_document.txt not found at {cleaned_doc_path}")
        return

    print(f"Reading cleaned document from: {cleaned_doc_path}")
    cleaned_text = cleaned_doc_path.read_text(encoding="utf-8")

    print("Running analyze_document_structure (with updated Prompt)...")
    try:
        struct_output = analyze_document_structure(cleaned_text)
        questions = struct_output.get("questions", [])
        
        # Inject pdf_stem and ids like pastpaper_extract does
        pdf_stem = "2024 II"
        for idx, q in enumerate(questions, start=1):
            q["pdf_stem"] = pdf_stem
            if "qno" in q and "question_id" not in q:
                q["question_id"] = str(q["qno"])
            if not q.get("question_id"):
                q["question_id"] = str(idx)

        print(f"Success! Extracted {len(questions)} questions.")

        # --- DETERMINISTIC DIAGRAM FIX ---
        print("Running deterministic diagram reassignment...")
        # 1. Map Questions to Line Ranges in Cleaned Text
        lines = cleaned_text.splitlines()
        q_ranges = [] # (q_id, start_line)
        current_q = None
        
        # Regex to find "Question X" lines
        import re
        for i, line in enumerate(lines):
            m = re.match(r"^Question\s+(\d+)", line, re.IGNORECASE)
            if m:
                q_id = int(m.group(1))
                q_ranges.append({"id": q_id, "start": i})
        
        # 2. Map Diagrams to Physical Line Numbers
        diagram_locs = [] # (filename, line_idx)
        for i, line in enumerate(lines):
            m = re.search(r"\[DIAGRAM:\s+(.*?)\]", line)
            if m:
                diagram_locs.append({"name": m.group(1), "line": i})
        
        # 3. Determine Correct Owner for each Diagram
        diagram_owners = {}
        for d in diagram_locs:
            # Find the Question range this line falls into
            # It belongs to the last Question whose start_line <= d.line
            owner = None
            for q in q_ranges:
                if q["start"] <= d["line"]:
                    owner = q["id"]
                else:
                    break
            if owner:
                diagram_owners[d["name"]] = owner
                print(f" -> Diagram {d['name']} physically belongs to Question {owner}")

        # 4. Fix JSON
        # Helper to recursively find diagram tags in JSON and remove them if wrong
        def remove_diagram_from_text(q_obj, d_name):
            if "text" in q_obj and f"[DIAGRAM: {d_name}]" in q_obj["text"]:
                print(f"    - Removing {d_name} from Q{q_obj.get('question_id', '?')}")
                q_obj["text"] = q_obj["text"].replace(f"[DIAGRAM: {d_name}]", "").strip()
            if "diagrams" in q_obj and f"[DIAGRAM: {d_name}]" in q_obj["diagrams"]:
                q_obj["diagrams"].remove(f"[DIAGRAM: {d_name}]")
            
            for sub in q_obj.get("subquestions", []):
                remove_diagram_from_text(sub, d_name)

        # Helper to inject diagram into correct Question
        def inject_diagram_to_q(q_list, target_id, d_name):
            found = False
            tag = f"[DIAGRAM: {d_name}]"
            
            for q in q_list:
                # Check main ID
                try:
                    qid = int(q.get("question_id", -1))
                except:
                    qid = -1
                
                if qid == target_id:
                    # Found the target question. Inject into main text for now (simplest)
                    if tag not in q.get("text", ""):
                        print(f"    + Injecting {d_name} into Q{target_id} text")
                        q["text"] = (q["text"] + "\n" + tag).strip()
                    return True
            return False

        # Apply Fixes
        for d_name, correct_q_id in diagram_owners.items():
            # First, scrub this diagram from ALL questions to remove duplicates/ghosts
            for q in questions:
                remove_diagram_from_text(q, d_name)
            
            # Then inject into the correct one
            inject_diagram_to_q(questions, correct_q_id, d_name)

        # ---------------------------------
        
        # Write back
        print(f"Writing updated blueprint to: {blueprint_path}")
        with open(blueprint_path, "w", encoding="utf-8") as f:
            json.dump(questions, f, indent=2, ensure_ascii=False)

        print("Done.")

    except Exception as e:
        print(f"Error analyzing document: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    fix_2024_ii_blueprint()
