"""Debug script to check why critic rejects valid stem."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from app.agents.critic import QualityCritic

# Test the exact stem from the test
stem = "Consider a university database system with students, courses, and enrollments. Each student has student ID, name, and email. Each course has course code, title, and credits. Students enroll in courses, and each enrollment has a grade."

critic = QualityCritic()
result = critic._check_placeholder_content(stem)

print(f"Stem length: {len(stem)}")
print(f"Full stem: {stem}")
print(f"Is placeholder: {result}")

# Check each condition
import re
text_lower = stem.lower().strip()
# Check word-boundary patterns
placeholder_patterns_word_boundary = [
    r'\btbd\b', r'\bna\b', r'\btba\b',
    r'\bn/a\b', r'\bfill in\b', r'\badd here\b'
]
for pattern in placeholder_patterns_word_boundary:
    if re.search(pattern, text_lower):
        print(f"  MATCHES WORD-BOUNDARY PATTERN: '{pattern}'")
# Check substring patterns
placeholder_patterns_substring = [
    "...", "to be added", "[insert", "[placeholder", "to be determined"
]
for pattern in placeholder_patterns_substring:
    if pattern in text_lower:
        print(f"  MATCHES SUBSTRING PATTERN: '{pattern}'")
has_alnum = bool(re.search(r'[a-zA-Z0-9]', stem))
print(f"  Has alphanumeric: {has_alnum}")
print(f"  Is empty: {not stem or not stem.strip()}")

# Check draft structure
draft = {
    "question_no": "Q1",
    "marks": 25,
    "text": stem,
    "subquestions": [
        {"label": "a", "marks": 5, "text": "Identify the main entities and their attributes."},
        {"label": "b", "marks": 10, "text": "Draw the ER diagram showing relationships and cardinalities."},
        {"label": "c", "marks": 10, "text": "Map the ER diagram to a relational schema."}
    ]
}

print(f"\nDraft structure:")
print(f"  question_no: {draft.get('question_no')}")
print(f"  marks: {draft.get('marks')}")
print(f"  text field exists: {'text' in draft}")
print(f"  text value: {draft.get('text', 'MISSING')[:100]}...")
print(f"  text length: {len(draft.get('text', ''))}")

# Check what critic sees
question_stem = draft.get("text", "").strip()
print(f"\nCritic sees:")
print(f"  question_stem: {question_stem[:100]}...")
print(f"  question_stem length: {len(question_stem)}")
print(f"  _check_placeholder_content result: {critic._check_placeholder_content(question_stem)}")

