"""
Answer Evaluation, Topic Detection, Lecture Topics, Feedback
(from evaluator.py, feedback.py, lecture_notes.py, adaptive_learning.py / services.py)
"""

import os
import re
import json
import time
import textwrap
from typing import Dict, Any, List, Optional

import fitz
from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

from app.core.config import settings


# ═══════════════════════════════════════════════════════════════
#  OpenAI Client  (updated sdk ≥1.0)
# ═══════════════════════════════════════════════════════════════

_client: Optional[OpenAI] = None


def get_openai_client() -> Optional[OpenAI]:
    global _client
    if _client is None and settings.OPENAI_API_KEY:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


# ═══════════════════════════════════════════════════════════════
#  Lecture Topics Extraction  (from lecture_notes.py)
# ═══════════════════════════════════════════════════════════════

def extract_lecture_topics() -> List[str]:
    """Extract key topics/headings from lecture-note PDFs."""
    topics: set = set()
    if not settings.LECTURE_DIR.exists():
        return []
    for file in os.listdir(settings.LECTURE_DIR):
        if not file.lower().endswith(".pdf"):
            continue
        try:
            doc = fitz.open(str(settings.LECTURE_DIR / file))
            for page in doc:
                text = page.get_text()
                for line in text.split("\n"):
                    line = line.strip()
                    # Headings: short all-caps lines
                    if len(line.split()) <= 8 and line.isupper():
                        topics.add(line.title())
                    # Numbered headings like "1.2 Normalization"
                    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", line):
                        topics.add(line)
            doc.close()
        except Exception:
            pass
    return list(topics)


# ═══════════════════════════════════════════════════════════════
#  Topic Detection  (from adaptive_learning.py / app.py)
# ═══════════════════════════════════════════════════════════════

def detect_topic(question: str) -> str:
    q = question.lower()
    if "sql" in q or "database" in q:
        return "Database"
    elif "process" in q or "cpu" in q:
        return "OperatingSystems"
    elif "network" in q or "protocol" in q:
        return "Networks"
    return "General"


# ═══════════════════════════════════════════════════════════════
#  Behaviour Metrics  (from evaluator.py)
# ═══════════════════════════════════════════════════════════════

def extract_behaviour_metrics(result: dict, user_answer: str) -> dict:
    """Extract concept count, mistakes, and answer length from evaluation."""
    strengths = result.get("feedback", {}).get("strengths", "")
    concept_count = len([x for x in strengths.split(",") if len(x.strip()) > 3])

    weaknesses = result.get("feedback", {}).get("weaknesses", "").lower()
    mistakes = 0
    if "missing" in weaknesses:
        mistakes += 1
    if "incorrect" in weaknesses:
        mistakes += 1
    if "lack" in weaknesses:
        mistakes += 1

    return {
        "concept_count": concept_count,
        "mistakes": mistakes,
        "answer_length": len(user_answer.split()),
    }


# ═══════════════════════════════════════════════════════════════
#  Model output validation (server-side)
# ═══════════════════════════════════════════════════════════════

class FeedbackPayload(BaseModel):
    strengths: str = ""
    weaknesses: str = ""
    improvements: str = ""


class EvaluationPayload(BaseModel):
    score: float = Field(ge=0, le=100)
    feedback: FeedbackPayload = FeedbackPayload()
    study_recommendations: List[str] = []
    next_level: Literal["easy", "medium", "hard"]


def _extract_json_object(text: str) -> Optional[dict]:
    """
    Best-effort extraction of a single JSON object from an LLM response.
    Handles cases where the model wraps JSON in prose or code fences.
    """
    if not text:
        return None
    s = text.strip()
    # Strip common fenced code blocks
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
        s = s.strip()
    start = s.find("{")
    end = s.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = s[start : end + 1]
    try:
        return json.loads(candidate)
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
#  Answer Evaluation  (from evaluator.py)
# ═══════════════════════════════════════════════════════════════

def evaluate_answer(user_answer: str, question_text: str, difficulty: str) -> dict:
    """Evaluate a student answer for a question using OpenAI (validated JSON output)."""
    lecture_topics = extract_lecture_topics()
    client = get_openai_client()

    threshold = settings.CORRECTNESS_THRESHOLD
    topics_preview = lecture_topics[:50]  # keep prompt bounded

    prompt = textwrap.dedent(
        f"""
        You are an expert university examiner.

        Question:
        {question_text}

        Student Answer:
        {user_answer}

        Difficulty Level: {difficulty}

        Lecture Topics (choose from these when recommending study):
        {topics_preview}

        TASKS:
        1) Score the student answer for correctness and completeness (0–100).
        2) Provide VERY SPECIFIC feedback:
           - strengths: what is correct / well-explained
           - weaknesses: what is incorrect / missing
           - improvements: what to add/change next time
        3) If score < {threshold} (treat as incorrect):
           - Provide 3–6 study_recommendations as short bullet-like strings
           - Each recommendation must include a topic and a brief reason (e.g., "Normalization — revisit 2NF/3NF to fix dependency errors")
        4) Recommend next_level adaptively: "easy" | "medium" | "hard".

        Return STRICT JSON only with this exact schema:
        {{
          "score": number,
          "feedback": {{
              "strengths": string,
              "weaknesses": string,
              "improvements": string
          }},
          "study_recommendations": [string],
          "next_level": "easy" | "medium" | "hard"
        }}
        """
    ).strip()

    fallback = {
        "score": 50,
        "feedback": {
            "strengths": "Evaluation unavailable — API not configured.",
            "weaknesses": "",
            "improvements": "Please configure OPENAI_API_KEY in backend/.env",
        },
        "study_recommendations": [],
        "next_level": difficulty,
        "behaviour": {
            "concept_count": 0,
            "mistakes": 0,
            "answer_length": len(user_answer.split()),
        },
        "_validated": False,
        "_fallback_used": True,
    }

    if not client:
        return fallback

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You evaluate answers like a strict examiner."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        raw = (resp.choices[0].message.content or "").strip()
        parsed_obj = _extract_json_object(raw)
        if parsed_obj is None:
            raise ValueError("Model did not return valid JSON")

        payload = EvaluationPayload.model_validate(parsed_obj).model_dump()
        payload["behaviour"] = extract_behaviour_metrics(payload, user_answer)
        payload["_validated"] = True
        payload["_fallback_used"] = False
        return payload
    except ValidationError as e:
        print(f"Evaluation validation error: {e}")
        fallback["feedback"]["strengths"] = "Evaluation failed validation; using fallback."
        return fallback
    except Exception as e:
        print(f"Evaluation error: {e}")
        fallback["feedback"]["strengths"] = f"Evaluation failed: {e}"
        return fallback


# ═══════════════════════════════════════════════════════════════
#  Standalone Feedback Logic  (from feedback.py)
# ═══════════════════════════════════════════════════════════════

def generate_feedback(score: float, level: str) -> dict:
    """Generate reward + message + next level (standalone, no OpenAI)."""
    if score >= 80:
        reward = 1.0
        msg = "Excellent understanding. You can move to higher difficulty."
    elif score >= 50:
        reward = 0.5
        msg = "Good attempt, but try to include more key points."
    else:
        reward = -0.5
        msg = "Answer lacks depth. Review concepts and try again."

    return {
        "score": score,
        "reward": reward,
        "message": msg,
        "next_level": adaptive_level(level, reward),
    }


def adaptive_level(current: str, reward: float) -> str:
    """Determine next difficulty level given current + reward."""
    levels = ["easy", "medium", "hard"]
    idx = levels.index(current)
    if reward > 0 and idx < 2:
        return levels[idx + 1]
    elif reward < 0 and idx > 0:
        return levels[idx - 1]
    return current
