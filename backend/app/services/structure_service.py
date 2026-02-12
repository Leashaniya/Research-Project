import sys
import re
from pathlib import Path
import os
import json
import openai

# Add the backend root to sys.path
backend_root = str(Path(__file__).resolve().parents[2])
if backend_root not in sys.path:
    sys.path.append(backend_root)
from app.core.config import OPENAI_API_KEY
from scripts.structure_topics_template import main
from app.core.paths import ARTIFACTS_DIR

def analyze_document_structure(cleaned_text: str, model="gpt-4") -> dict:
    """
    Analyzes document text and extracts a structured exam blueprint.
    """
    if not OPENAI_API_KEY:
        raise EnvironmentError("AI Cloud API Key is missing. Please check your .env file.")

    print("Initializing Intelligence Engine for structure analysis...")
    # Force use of official OpenAI Cloud URL
    client = openai.OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")

    print("Analyzing document structure...") 

    system_prompt = (
        "You are a document structuring engine; do not invent; preserve wording; detect Question 1..; "
        "detect a), b) and nested i., ii.; extract marks; ignore headers/footers; "
        "CRITICAL RULES FOR DIAGRAMS:"
        "1. PRESERVE ALL [DIAGRAM: ...] tags."
        "2. SPATIAL LOCALITY: Keep the diagram tag associated with the text IMMEDIATELY SURROUNDING IT."
        "3. Do NOT move a diagram from Question 3 to Question 1."
        "4. If a diagram appears between Question 3 and Question 4, it likely belongs to the preceding question (Question 3)."
        "5. Place the tag inside the 'text' field of the subgroup or question it physically sits next to."
    )

    user_prompt = f"""
    Structure the following exam text into JSON format with the schema:
    {{
        "questions": [
            {{
                "question_id": int,
                "marks": int|null,
                "text": str,
                "subquestions": [...]
            }}
        ],
        "totals": {{ "paper_total": int|null, "detected_total": int|null }},
        "warnings": [str]
    }}

    Text:
    {cleaned_text}
    """

    model_name = "gpt-4o-mini"
    
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0,
            response_format={"type": "json_object"}
        )

        structured_text = response.choices[0].message.content.strip()
        result_json = json.loads(structured_text)

        # --- DETERMINISTIC DIAGRAM FIX ---
        # Map Diagrams to Questions based on physical line location in text
        try:
            questions = result_json.get("questions", [])
            lines = cleaned_text.splitlines()
            q_ranges = []
            
            # 1. Map Questions to Line Ranges
            for i, line in enumerate(lines):
                m = re.match(r"^Question\s+(\d+)", line, re.IGNORECASE)
                if m:
                    q_id = int(m.group(1))
                    q_ranges.append({"id": q_id, "start": i})
            
            # 2. Map Diagrams to Line Numbers
            diagram_locs = [] # (filename, line_idx)
            for i, line in enumerate(lines):
                m = re.search(r"\[DIAGRAM:\s+(.*?)\]", line)
                if m:
                    diagram_locs.append({"name": m.group(1), "line": i})
            
            # 3. Determine Correct Owner
            if q_ranges and diagram_locs:
                diagram_owners = {}
                for d in diagram_locs:
                    owner = None
                    for q in q_ranges:
                        if q["start"] <= d["line"]:
                            owner = q["id"]
                        else:
                            break
                    if owner:
                        diagram_owners[d["name"]] = owner
            
                # 4. Apply Fixes (Scan & Reassign)
                def remove_diagram_from_text(q_obj, d_name):
                    if "text" in q_obj and f"[DIAGRAM: {d_name}]" in q_obj["text"]:
                        q_obj["text"] = q_obj["text"].replace(f"[DIAGRAM: {d_name}]", "").strip()
                    if "diagrams" in q_obj and f"[DIAGRAM: {d_name}]" in q_obj["diagrams"]:
                        q_obj["diagrams"].remove(f"[DIAGRAM: {d_name}]")
                    for sub in q_obj.get("subquestions", []):
                        remove_diagram_from_text(sub, d_name)

                def inject_diagram_to_q(q_list, target_id, d_name):
                    tag = f"[DIAGRAM: {d_name}]"
                    for q in q_list:
                        # Locate target question
                        try:
                            qid = int(q.get("question_id", -1))
                        except:
                            qid = -1
                        if qid == target_id:
                            if tag not in q.get("text", ""):
                                # Start new line for diagram to keep it clean
                                q["text"] = (q["text"] + "\n" + tag).strip()
                            return True
                    return False

                for d_name, correct_q_id in diagram_owners.items():
                    # Move to correct Q
                    for q in questions:
                        remove_diagram_from_text(q, d_name)
                    inject_diagram_to_q(questions, correct_q_id, d_name)
                    
        except Exception as e:
            print(f"Warning: Deterministic Diagram Fix failed: {e}. detailed_error={e}")

        return result_json

    except Exception as e:
        raise RuntimeError(f"Structure analysis failed: {e}")

def ensure_structure_artifacts():
    """
    Ensures that the topic clustering and templates are built from extracted data.
    """
    req = [
        ARTIFACTS_DIR / "exam_blueprint_template.json",
        ARTIFACTS_DIR / "template_questions.json",
    ]
    if all(Path(p).exists() for p in req):
        return {"status": "ok", "message": "Artifacts already exist."}

    main()
    return {"status": "built", "message": "Artifacts created by structure_topics_template.py"}
