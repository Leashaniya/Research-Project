"""
Validate agentic_model_paper.json: check that all questions and subquestions have non-empty text
so the PDF can render full content. Run from service root: python scripts/validate_paper_json.py
"""
import json
import sys
from pathlib import Path

# Service root = parent of scripts/
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_ROOT = SCRIPT_DIR.parent
PAPER_JSON = SERVICE_ROOT / "data" / "outputs" / "model_papers" / "agentic_model_paper.json"


def validate_subquestions(subs, path_prefix="", issues=None):
    if issues is None:
        issues = []
    for i, sq in enumerate(subs):
        if not isinstance(sq, dict):
            issues.append(f"{path_prefix}[{i}] is not a dict")
            continue
        label = sq.get("label", "?")
        text = sq.get("text")
        if text is None:
            issues.append(f"{path_prefix} subquestion {label}: missing 'text'")
        elif not str(text).strip():
            issues.append(f"{path_prefix} subquestion {label}: empty 'text'")
        nested = sq.get("subquestions", [])
        if nested:
            validate_subquestions(nested, f"{path_prefix}{label}) ", issues)
    return issues


def main():
    if not PAPER_JSON.exists():
        print(f"Paper JSON not found: {PAPER_JSON}")
        sys.exit(1)

    with open(PAPER_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data.get("questions", [])
    if not questions:
        print("No 'questions' array or empty.")
        sys.exit(1)

    issues = []
    for q_idx, q in enumerate(questions):
        q_no = q.get("question_no", f"Q{q_idx+1}")
        text = q.get("text")
        if text is None:
            issues.append(f"{q_no}: missing question 'text'")
        elif not str(text).strip():
            issues.append(f"{q_no}: empty question 'text'")
        subs = q.get("subquestions", [])
        validate_subquestions(subs, f"{q_no} ", issues)

    print(f"Validated {len(questions)} questions in {PAPER_JSON.name}")
    if issues:
        print(f"\nIssues found ({len(issues)}):")
        for msg in issues:
            print(f"  - {msg}")
        sys.exit(1)
    print("All questions and subquestions have non-empty text. JSON is valid for PDF generation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
