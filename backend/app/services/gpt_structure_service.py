import sys
from pathlib import Path

# Add the project root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[2]))

import openai
import os
import json
from app.core.config import OPENAI_API_KEY

def gpt_structure_exam(cleaned_text: str, model="gpt-4") -> dict:
    """
    Use OpenAI GPT to structure exam questions from cleaned text.

    Args:
        cleaned_text (str): The cleaned document text.
        model (str): The OpenAI model to use (default: "gpt-4").

    Returns:
        dict: The structured exam data including questions, totals, and warnings.
    """
    if not OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY is not set. Please check your .env file.")

    print("Initializing OpenAI client...")
    client = openai.OpenAI()

    print("Calling GPT for structuring exam...")  # Debug statement

    system_prompt = (
        "You are a document structuring engine; do not invent; preserve wording; detect Question 1..; "
        "detect a), b) and nested i., ii.; extract marks; ignore headers/footers like Page x of y, dates, codes; "
        "keep [DIAGRAM: ...] placeholders."
    )

    user_prompt = f"""
    Structure the following exam text into JSON format with the schema:
    {{
        "questions": [
            {{
                "qno": int,
                "marks": int|null,
                "text": str,
                "subquestions": [
                    {{
                        "label": str,
                        "marks": int|null,
                        "text": str,
                        "subquestions": [...]
                    }}
                ]
            }}
        ],
        "totals": {{
            "paper_total": int|null,
            "detected_total": int|null
        }},
        "warnings": [str]
    }}

    Text:
    {cleaned_text}
    """

    try:
        response = client.responses.create(
        model=model,
        input=user_prompt,
        temperature=0,
        max_output_tokens=3000
        )


        structured_text = response.output_text.strip()
        return json.loads(structured_text)

    except Exception as e:
        raise RuntimeError(f"GPT structuring failed: {e}")
