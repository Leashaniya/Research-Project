import sys
from pathlib import Path

# Add the backend root to sys.path
backend_root = str(Path(__file__).resolve().parents[2])
if backend_root not in sys.path:
    sys.path.append(backend_root)

from pathlib import Path
import os
import json
import openai
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
        "keep [DIAGRAM: ...] placeholders."
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
        return json.loads(structured_text)

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
