"""
Question Extraction, Formatting & Question Bank
(from question_extractor.py / services.py)
"""

import os
import re
import time
import json
from typing import List, Optional

import fitz

from app.core.config import settings
from app.services.evaluation_service import get_openai_client, detect_topic
from app.services.bloom_classifier import classify_bloom_level
from app.services.rl_engine import rl_engine


def _log_extracted_question(entry: dict) -> None:
    """Append a single extracted question with metadata to the log file."""
    try:
        with open(settings.EXTRACTION_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except Exception as e:
        print(f"✗ Failed to write extraction log: {e}")


# ═══════════════════════════════════════════════════════════════
#  Question Extraction & Formatting  (from question_extractor.py)
# ═══════════════════════════════════════════════════════════════

def normalize_pdf_text(text: str) -> str:
    """Fix PDF line-break artifacts."""
    lines = text.split("\n")
    rebuilt: List[str] = []
    buffer = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not buffer:
            buffer = line
        elif buffer[-1] not in ".?:":
            buffer += " " + line
        else:
            rebuilt.append(buffer)
            buffer = line
    if buffer:
        rebuilt.append(buffer)
    return " ".join(rebuilt)


def clean_question(q: str) -> str:
    return re.sub(r"\s+", " ", q).strip()


def is_valid_question(q: str) -> bool:
    """Filter out noise, theory statements, and diagram questions."""
    if len(q.split()) < 5:
        return False

    theory_keywords = (
        "refers to", "is the", "consists of", "includes",
        "comprises", "we discuss", "shows that",
    )
    if any(k in q.lower() for k in theory_keywords):
        return False

    interrogatives = (
        "what", "who", "which", "when", "where", "how",
        "find", "calculate", "determine", "list", "compute", "show",
    )
    if not any(w in q.lower() for w in interrogatives) and not q.strip().endswith("?"):
        return False

    forbidden = (
        "draw", "illustrate", "diagram", "figure", "chart",
        "graph", "table", "depict", "show the", "extendible hashed",
        "b+ tree", "shown below", "that appears",
    )
    if any(k in q.lower() for k in forbidden):
        return False

    return True


def format_question_with_openai(raw_question: str) -> str:
    """Format a raw question using OpenAI into proper academic style."""
    client = get_openai_client()
    if not client:
        return raw_question

    prompt = (
        "You are an expert university lecturer creating exam questions for a "
        "Database Management Systems course.\n\n"
        "Below is a raw question extracted from lecture materials/past papers. "
        "Your task is to:\n"
        "1. Format it into proper academic question style\n"
        "2. Add a relevant real-world scenario if the question is theoretical\n"
        "3. Structure it with sub-parts (a, b, c) if it's a complex topic\n"
        "4. Use appropriate academic language\n\n"
        f'Raw question: "{raw_question}"\n\n'
        "Guidelines:\n"
        "- If the question asks about definitions (\"what is\", \"define\"), "
        "add a scenario and ask for examples\n"
        "- If the question asks about processes (\"how does\", \"explain the process\"), "
        "break it into steps\n"
        "- If the question asks about comparisons (\"compare\", \"difference between\"), "
        "structure as a,b,c parts\n"
        "- If the question is already well-formatted, enhance it slightly\n"
        "- Draw scenarios from: university database, e-commerce, hospital system, "
        "banking, library system\n\n"
        "Return ONLY the formatted question text, nothing else."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You format academic database questions professionally."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=300,
        )
        result = resp.choices[0].message.content.strip().strip("'\"")
        time.sleep(0.5)
        return result
    except Exception as e:
        print(f"OpenAI formatting error: {e}")
        return raw_question


def add_scenario_to_question(raw_question: str) -> str:
    """Add a real-world scenario to theoretical questions."""
    client = get_openai_client()
    if not client:
        return raw_question

    prompt = (
        "You are creating exam questions for a Database course. "
        "Add a relevant real-world scenario to this question:\n\n"
        f'Original question: "{raw_question}"\n\n'
        "Choose a scenario from:\n"
        "- University/SLIIT student enrollment system\n"
        "- Hospital patient management system\n"
        "- E-commerce platform (Amazon-like)\n"
        "- Banking transaction system\n"
        "- Library management system\n"
        "- Airline reservation system\n\n"
        "Make the question engaging and practical. Return ONLY the enhanced question with scenario."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You add practical scenarios to database questions."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=250,
        )
        result = resp.choices[0].message.content.strip().strip("'\"")
        time.sleep(0.5)
        return result
    except Exception as e:
        print(f"Scenario addition error: {e}")
        return raw_question


def smart_format_question(raw_question: str) -> str:
    """Detect question type and apply appropriate formatting."""
    q_lower = raw_question.lower()
    definition_kw = ["what is", "define", "explain", "describe", "what are"]
    if any(kw in q_lower for kw in definition_kw):
        return add_scenario_to_question(raw_question)
    return format_question_with_openai(raw_question)


def extract_questions_from_text(raw_text: str) -> List[str]:
    """Extract and format questions from a page of PDF text."""
    text = normalize_pdf_text(raw_text)

    # Remove noise
    text = re.sub(r"Question\s*\d+", "", text, flags=re.I)
    text = re.sub(r"\(\d+\s*marks?\)", "", text, flags=re.I)
    text = re.sub(r"Page\s*\d+.*", "", text, flags=re.I)
    text = re.sub(r"--.*?--", "", text)

    # Split by sub-question labels
    parts = re.split(r"(?:^|\s)(?:[a-z]\)|[ivx]+\.)\s+", text, flags=re.I)

    questions: List[str] = []
    total_parts = len(parts)

    for idx, part in enumerate(parts):
        part = clean_question(part)
        if is_valid_question(part):
            print(f"Formatting question {idx+1}/{total_parts}...")
            try:
                formatted = smart_format_question(part)
                questions.append(formatted)
                print(f"✓ Formatted: {formatted[:100]}...")
            except Exception as e:
                print(f"✗ Failed to format, using original: {e}")
                questions.append(part)

    return questions


def batch_format_questions(question_list: list) -> list:
    """Format a list of questions using OpenAI (can be called separately)."""
    formatted_questions = []
    for i, q in enumerate(question_list):
        print(f"Formatting question {i+1}/{len(question_list)}")
        if isinstance(q, dict):
            raw_q = q.get("question", "")
            formatted = smart_format_question(raw_q)
            q["question"] = formatted
            q["formatted"] = True
            formatted_questions.append(q)
        else:
            formatted = smart_format_question(q)
            formatted_questions.append(formatted)
        time.sleep(0.5)
    return formatted_questions


# ═══════════════════════════════════════════════════════════════
#  Question Bank  (from app.py read_pdfs / caching)
# ═══════════════════════════════════════════════════════════════

class QuestionBank:
    """Loads, caches, and serves questions from PDF files."""

    def __init__(self):
        self.questions: List[dict] = []
        self._loaded = False
        # Per-difficulty cursors so selection is deterministic instead of random
        self._cursor = {"easy": 0, "medium": 0, "hard": 0}

    def load(self, force: bool = False):
        """Walk Data/ directory, extract questions from all PDFs."""
        if self._loaded and not force:
            return
        self.questions = []
        if not settings.DATA_DIR.exists():
            self._loaded = True
            return

        print(f"Scanning directory: {settings.DATA_DIR}")
        pdf_found = False

        for root, _, files in os.walk(settings.DATA_DIR):
            for fname in files:
                if not fname.lower().endswith(".pdf"):
                    continue
                pdf_found = True
                pdf_path = os.path.join(root, fname)
                print(f"Found PDF: {pdf_path}")
                try:
                    doc = fitz.open(pdf_path)
                    print(f"Opened PDF: {fname}, pages: {len(doc)}")
                    for page_num, page in enumerate(doc):
                        text = page.get_text()
                        print(f"Page {page_num + 1} text length: {len(text)}")
                        if not text.strip():
                            continue
                        qs = extract_questions_from_text(text)
                        print(f"Extracted {len(qs)} questions from page {page_num + 1}")
                        for q in qs:
                            difficulty = classify_bloom_level(q)
                            topic = detect_topic(q)
                            record = {
                                "question": q,
                                "bloom_level": None,  # Local model doesn't provide Bloom levels
                                "difficulty": difficulty,
                                "topic": topic,
                                "source": fname,
                                "page": page_num + 1,
                            }
                            self.questions.append(record)
                            _log_extracted_question(record)
                    doc.close()
                    print(f"  ✓ {fname}")
                except Exception as e:
                    print(f"  ✗ Error reading {pdf_path}: {e}")

        if not pdf_found:
            print("No PDF files found in the Data directory")
        else:
            print(f"Total questions extracted: {len(self.questions)}")
            easy = sum(1 for q in self.questions if q.get("difficulty") == "easy")
            medium = sum(1 for q in self.questions if q.get("difficulty") == "medium")
            hard = sum(1 for q in self.questions if q.get("difficulty") == "hard")
            unknown = len(self.questions) - (easy + medium + hard)
            print(f"Difficulty breakdown → easy={easy}, medium={medium}, hard={hard}, unknown={unknown}")

        self._loaded = True

    def get_question(self, difficulty: str) -> Optional[dict]:
        """Select a question using RL-influenced selection within the specified difficulty."""
        if not self.questions:
            return None

        # Filter strictly by stored difficulty field
        filtered = [q for q in self.questions if q["difficulty"] == difficulty]
        print(f"Found {len(filtered)} questions for difficulty '{difficulty}' "
              f"out of {len(self.questions)} total")

        if not filtered:
            # No questions found for this difficulty - return None instead of fallback
            print(f"No questions available for difficulty '{difficulty}'")
            return None

        # Use RL engine for ordering within the same difficulty, with deterministic tie-breaks
        policy = rl_engine.policy
        if policy and len(policy) > 0:
            filtered.sort(
                key=lambda q: (
                    -policy.get(f"{difficulty}_{q['topic']}", 0),
                    q.get("source", ""),
                    q.get("page", 0),
                    q.get("question", ""),
                )
            )
        else:
            # Stable, deterministic order when no policy is present
            filtered.sort(
                key=lambda q: (
                    q.get("source", ""),
                    q.get("page", 0),
                    q.get("question", ""),
                )
            )

        # Deterministic round-robin selection per difficulty
        idx = self._cursor.get(difficulty, 0) % len(filtered)
        self._cursor[difficulty] = idx + 1
        return filtered[idx]

    @property
    def count(self) -> int:
        return len(self.questions)

    def get_pdf_list(self) -> List[str]:
        pdfs: List[str] = []
        if settings.DATA_DIR.exists():
            for root, _, files in os.walk(settings.DATA_DIR):
                for f in files:
                    if f.lower().endswith(".pdf"):
                        pdfs.append(f)
        return pdfs


question_bank = QuestionBank()
