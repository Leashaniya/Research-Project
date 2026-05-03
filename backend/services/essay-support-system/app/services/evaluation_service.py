"""
Answer Evaluation, Topic Detection, Lecture Topics, Feedback
(from evaluator.py, feedback.py, lecture_notes.py, adaptive_learning.py / services.py)
"""

import os
import re
import json
import textwrap
from typing import Dict, Any, List, Optional

import fitz
import httpx
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
#  Topic Detection  (FIXED - extracts specific topic via OpenAI)
# ═══════════════════════════════════════════════════════════════

def detect_topic(question: str) -> str:
    """Extract specific academic topic from the question using OpenAI.
    Falls back to a truncated version of the question if API is unavailable.
    """
    client = get_openai_client()
    if not client:
        # Fallback: return truncated question as topic
        q = question.strip()
        return q[:80] if len(q) > 80 else q

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract the specific academic topic from this exam question in 3-6 words. "
                        "Return only the topic name, nothing else. "
                        "Examples: 'Functional Dependency', 'TCP/IP Protocol', 'Process Scheduling', "
                        "'Database Normalization', 'Binary Search Trees'"
                    ),
                },
                {"role": "user", "content": question},
            ],
            temperature=0,
            max_tokens=20,
        )
        topic = (resp.choices[0].message.content or "").strip()
        return topic if topic else question[:80]
    except Exception:
        return question[:80]


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
    detected_topic = detect_topic(question_text)

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
        "topic": detect_topic(question_text),
        "question_text": question_text,
        "recommendation": "",
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
        payload["topic"] = detected_topic          # specific topic extracted by AI
        payload["question_text"] = question_text   # full question for n8n context

        # Generate recommendation only if score < threshold (incorrect)
        score_normalized = payload["score"] / 100.0
        if score_normalized < 0.6:
            study_recs = payload.get("study_recommendations", [])
            if study_recs:
                payload["recommendation"] = study_recs[0]
            else:
                payload["recommendation"] = (
                    f"Revise {detected_topic} concepts to improve your understanding."
                )
        else:
            payload["recommendation"] = ""

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


# ═══════════════════════════════════════════════════════════════
#  Practice Questions Generator  (local fallback only)
# ═══════════════════════════════════════════════════════════════

def generate_practice_questions(topic: str) -> List[str]:
    """Generate practice questions locally as fallback when n8n is unavailable."""
    if not topic or not isinstance(topic, str):
        return []

    topic_lower = topic.lower().strip()

    # Database topics
    if any(k in topic_lower for k in ["sql", "database", "normalization", "functional dependency",
                                       "relational", "join", "key", "schema", "table"]):
        if "normalization" in topic_lower:
            return [
                "What is Normalization and why is it important in database design?",
                "Explain First Normal Form (1NF) with a practical example",
                "How does Second Normal Form (2NF) eliminate partial dependency?",
                "Explain Third Normal Form (3NF) with a real-world scenario",
                "Compare BCNF with 3NF — when would you use each?",
            ]
        elif "functional dependency" in topic_lower:
            return [
                "What is a functional dependency in a relational database?",
                "Explain Armstrong's Axioms with examples",
                "What is the difference between trivial and non-trivial functional dependencies?",
                "How do functional dependencies relate to database normalization?",
                "Provide an e-commerce example where functional dependencies apply",
            ]
        elif "join" in topic_lower:
            return [
                "What is a SQL JOIN and why is it needed?",
                "Explain INNER JOIN with a student-course example",
                "What is the difference between LEFT JOIN and RIGHT JOIN?",
                "Explain FULL OUTER JOIN with a practical scenario",
                "When would you use a CROSS JOIN?",
            ]
        elif any(k in topic_lower for k in ["key", "superkey", "candidate", "primary"]):
            return [
                "What is a superkey in a relational database?",
                "Explain the difference between a candidate key and a primary key",
                "What is a foreign key and how does it enforce referential integrity?",
                "Define prime attribute and non-prime attribute with examples",
                "Provide a university database scenario illustrating all key types",
            ]
        else:
            return [
                f"Define the concept of {topic} in the context of relational databases",
                f"Explain how {topic} is used in database design with an example",
                f"What problems does {topic} solve in database management?",
                f"Compare {topic} with a related database concept",
                f"Provide a real-world scenario where {topic} is applied",
            ]

    # Operating Systems topics
    elif any(k in topic_lower for k in ["process", "cpu", "operating", "scheduling",
                                         "thread", "memory", "deadlock", "semaphore"]):
        if "scheduling" in topic_lower:
            return [
                "What is process scheduling and why is it important?",
                "Explain FCFS scheduling with a Gantt chart example",
                "How does Shortest Job First (SJF) scheduling work?",
                "Compare Round Robin with Priority scheduling",
                "What is the role of the dispatcher in process scheduling?",
            ]
        elif "deadlock" in topic_lower:
            return [
                "What is a deadlock in operating systems?",
                "Explain the four necessary conditions for deadlock",
                "How does the Banker's Algorithm prevent deadlock?",
                "Compare deadlock prevention vs deadlock avoidance",
                "Give a real-world analogy for deadlock",
            ]
        else:
            return [
                f"What is {topic} in operating systems?",
                f"Explain the core principles of {topic}",
                f"Provide examples of {topic} in modern operating systems",
                f"What are the challenges involved in {topic}?",
                f"How does {topic} affect system performance?",
            ]

    # Network topics
    elif any(k in topic_lower for k in ["network", "protocol", "tcp", "ip", "osi",
                                         "routing", "socket", "http", "dns"]):
        if any(k in topic_lower for k in ["tcp", "ip"]):
            return [
                "What is the TCP/IP model and how does it differ from the OSI model?",
                "Explain the TCP three-way handshake step by step",
                "What is the difference between TCP and UDP?",
                "How does IP addressing and subnetting work?",
                "Explain how data is encapsulated as it moves through TCP/IP layers",
            ]
        else:
            return [
                f"What is {topic} and what problem does it solve?",
                f"Explain the core concepts of {topic} in computer networks",
                f"Provide examples of {topic} in real-world networking",
                f"What are the advantages and limitations of {topic}?",
                f"How does {topic} interact with other network protocols?",
            ]

    # Programming / Algorithms / Data Structures
    elif any(k in topic_lower for k in ["algorithm", "data structure", "sorting",
                                         "tree", "graph", "recursion", "complexity"]):
        return [
            f"What is {topic} and when would you use it?",
            f"Explain the working of {topic} with a step-by-step example",
            f"What is the time complexity of {topic} and why?",
            f"Compare {topic} with an alternative approach",
            f"Write pseudocode to implement {topic}",
        ]

    # General / unknown topic — use the full topic string for specificity
    else:
        return [
            f"Define {topic} in your own words",
            f"Explain the fundamental concepts of {topic} with an example",
            f"How is {topic} applied in a real-world context?",
            f"What are the key benefits and limitations of {topic}?",
            f"Compare {topic} with a related concept in the same field",
        ]


# ═══════════════════════════════════════════════════════════════
#  n8n Webhook Integration  (FIXED - sends full question context)
# ═══════════════════════════════════════════════════════════════

async def call_n8n_webhook(evaluation_result: dict) -> Optional[List[str]]:
    """Send evaluation result to n8n webhook and get practice questions."""

    SEP = "─" * 60

    # ── Pass/fail check ──────────────────────────────────────────
    overall_score  = evaluation_result.get("overall_score", None)
    correct_answers = evaluation_result.get("correct_answers", 0)
    total_answers   = evaluation_result.get("total_answers", 1)

    if overall_score is not None:
        passed = overall_score >= 60
    else:
        passed = (correct_answers / total_answers) >= 0.6 if total_answers > 0 else False

    if passed:
        print(f"\n{SEP}")
        print(f"  [N8N] SKIPPED — student passed (score: {overall_score}%)")
        print(f"{SEP}\n")
        return None

    # ── URL guard ────────────────────────────────────────────────
    if not settings.N8N_WEBHOOK_URL:
        print(f"\n{SEP}")
        print(f"  [N8N] ERROR — N8N_WEBHOOK_URL is not set in .env")
        print(f"{SEP}\n")
        return None

    # ── Build payload ────────────────────────────────────────────
    # CRITICAL FIX: Always use original topic, never question_text
    # question_text contains the first question which overwrites the topic name
    topic_for_n8n = evaluation_result.get("topic", "General")
    
    # Debug logging to ensure topic is correct
    print(f"🔍 [N8N] TOPIC DEBUG:")
    print(f"    Original topic: {evaluation_result.get('topic', 'NOT_FOUND')}")
    print(f"    question_text (ignored): {evaluation_result.get('question_text', 'NOT_FOUND')[:50] if evaluation_result.get('question_text') else 'NOT_FOUND'}")
    print(f"    Final topic_for_n8n: {topic_for_n8n}")

    feedback_data = evaluation_result.get("feedback", "")
    if isinstance(feedback_data, dict):
        weaknesses = feedback_data.get("weaknesses", "")
    else:
        weaknesses = str(feedback_data)

    n8n_payload = {
        "topic":          topic_for_n8n,
        "feedback":       weaknesses,
        "recommendation": evaluation_result.get("recommendation", ""),
    }

    # ══ REQUEST LOG ══════════════════════════════════════════════
    print(f"\n{SEP}")
    print(f"  [N8N] ▶ OUTGOING REQUEST")
    print(f"{SEP}")
    print(f"  URL     : {settings.N8N_WEBHOOK_URL}")
    print(f"  METHOD  : POST")
    print(f"  PAYLOAD :")
    print(f"    topic          : {n8n_payload['topic'][:120]}")
    print(f"    feedback       : {n8n_payload['feedback'][:120]}")
    print(f"    recommendation : {n8n_payload['recommendation'][:120]}")
    print(f"  ✅ FINAL TOPIC SENT TO N8N: '{topic_for_n8n}'")
    print(f"{SEP}\n")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                settings.N8N_WEBHOOK_URL,
                json=n8n_payload,
            )

        # ══ RESPONSE LOG ═════════════════════════════════════════
        print(f"\n{SEP}")
        print(f"  [N8N] ◀ INCOMING RESPONSE")
        print(f"{SEP}")
        print(f"  STATUS  : {response.status_code}")
        print(f"  HEADERS :")
        for k, v in response.headers.items():
            print(f"    {k}: {v}")
        print(f"  RAW BODY: {response.text[:500] if response.text.strip() else '(empty)'}")
        print(f"{SEP}\n")

        if response.status_code != 200:
            print(f"  [N8N] ✖ HTTP error {response.status_code} — falling back to local")
            return None

        if not response.text.strip():
            print(f"  [N8N] ✖ Empty response body — falling back to local")
            return None

        # ── Parse JSON ───────────────────────────────────────────
        try:
            n8n_response = response.json()
        except Exception as json_error:
            print(f"  [N8N] ✖ JSON parse failed: {json_error}")
            print(f"  [N8N]   Raw text was: '{response.text[:300]}'")
            return None

        questions = (
            n8n_response.get("practice_questions")
            or n8n_response.get("questions")
        )

        # ══ PROCESSED RESULT LOG ═════════════════════════════════
        print(f"\n{SEP}")
        print(f"  [N8N] ✔ PROCESSED RESPONSE")
        print(f"{SEP}")
        print(f"  status   : {n8n_response.get('status', 'n/a')}")
        print(f"  message  : {n8n_response.get('message', 'n/a')}")
        print(f"  questions: {len(questions) if isinstance(questions, list) else 0} received")
        if isinstance(questions, list):
            for idx, q in enumerate(questions, 1):
                print(f"    {idx}. {q}")
        print(f"{SEP}\n")

        if questions and isinstance(questions, list) and len(questions) > 0:
            return questions

        print(f"  [N8N] ✖ No valid questions in response — falling back to local")
        return None

    except Exception as e:
        print(f"\n{SEP}")
        print(f"  [N8N] ✖ EXCEPTION: {type(e).__name__}: {e}")
        print(f"{SEP}\n")
        return None


async def get_practice_questions_with_fallback(evaluation_result: dict) -> List[str]:
    """Get practice questions from n8n; fall back to local generation if n8n fails."""
    # Try n8n webhook first
    questions = await call_n8n_webhook(evaluation_result)

    # Fallback to local generation if n8n fails or returns empty
    if not questions:
        topic = evaluation_result.get("topic", "General")
        questions = generate_practice_questions(topic)
        print(f"Using local practice questions as fallback for topic: {topic}")

    return questions


def _strip_code_fence_json(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    inner: List[str] = []
    for line in lines[1:]:
        if line.strip().startswith("```"):
            break
        inner.append(line)
    return "\n".join(inner).strip()


def _coerce_correct_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        s = val.lower().strip()
        if s in ("true", "1", "yes"):
            return True
        if s in ("false", "0", "no"):
            return False
    if isinstance(val, (int, float)):
        if val == 1:
            return True
        if val == 0:
            return False
    return None


def _normalize_practice_answer_keys(practice_answers: Dict[Any, str], n: int) -> Dict[int, str]:
    """
    Preserve exact order. No shifting, no overwriting.
    """
    print(f" [NORMALIZE] Input practice_answers: {practice_answers}")
    print(f" [NORMALIZE] Input keys: {list(practice_answers.keys())}")
    print(f" [NORMALIZE] Input values: {list(practice_answers.values())}")
    print(f" [NORMALIZE] Number of questions (n): {n}")
    
    normalized = {}
    for i in range(n):
        answer = practice_answers.get(i, "No answer")
        if answer is None or str(answer).strip() == "":
            answer = "No answer"
        normalized[i] = str(answer).strip()
        print(f" [NORMALIZE]   - Index {i}: key={i}, value='{answer}' -> normalized[{i}]='{normalized[i]}'")
    
    print(f" [NORMALIZE] Final normalized: {normalized}")
    return normalized


def _merge_llm_and_fallback_practice(
    llm: Dict[str, Any],
    fb: Dict[str, Any],
    num_questions: int,
) -> Dict[str, Any]:
    """
    UI expects one entry per question in question_results with a real boolean `correct`.
    The model may omit question_results or mark sound answers wrong — merge with local
    fallback so heuristic passes are preserved and LLM can still add passes.
    """
    fb_qr: List[dict] = fb.get("question_results") or []
    llm_qr = llm.get("question_results")
    if not isinstance(llm_qr, list):
        llm_qr = []

    def _llm_row_for_index(i: int) -> Optional[dict]:
        want = i + 1
        for item in llm_qr:
            if isinstance(item, dict) and item.get("question_number") == want:
                return item
        if i < len(llm_qr) and isinstance(llm_qr[i], dict):
            return llm_qr[i]
        return None

    merged_results: List[Dict[str, Any]] = []
    correct_count = 0
    for i in range(num_questions):
        fb_item = fb_qr[i] if i < len(fb_qr) else {}
        fb_ok = bool(fb_item.get("correct"))
        li = _llm_row_for_index(i)
        llm_ok = _coerce_correct_bool(li.get("correct")) is True if isinstance(li, dict) else False
        final_ok = fb_ok or llm_ok
        if final_ok:
            correct_count += 1
        fb_text = (fb_item.get("feedback") or "").strip()
        llm_text = ""
        if isinstance(li, dict) and li.get("feedback") is not None:
            llm_text = str(li.get("feedback")).strip()
        feedback = llm_text if llm_text else (fb_text or "No specific feedback.")
        merged_results.append(
            {"question_number": i + 1, "correct": final_ok, "feedback": feedback}
        )

    out = dict(llm)
    out["question_results"] = merged_results
    out["correct_answers"] = correct_count
    out["total_answers"] = num_questions
    if num_questions > 0:
        out["overall_score"] = round((correct_count / num_questions) * 100, 1)
    return out


async def evaluate_practice_answers(practice_answers: Dict[int, str], practice_questions: List[str], topic: str) -> Dict[str, Any]:
    """Evaluate student's practice answers using OpenAI."""
    print(f" [EVALUATION] Starting evaluation with {len(practice_answers)} answers and {len(practice_questions)} questions")
    
    # Debug validation logs
    print(f" [EVALUATION] Questions: {len(practice_questions)}")
    print(f" [EVALUATION] Answers: {len(practice_answers)}")
    print(f" [EVALUATION] Answer keys: {list(practice_answers.keys())}")
    
    # Validate count matching - be more flexible with key structures
    if len(practice_answers) > len(practice_questions):
        print(f" [EVALUATION] WARNING: More answers than questions, using first {len(practice_questions)}")
    elif len(practice_answers) < len(practice_questions):
        print(f" [EVALUATION] WARNING: Fewer answers than questions, missing answers will be 'No answer'")

    practice_answers = _normalize_practice_answer_keys(practice_answers, len(practice_questions))
    print(f" [EVALUATION] Normalized practice_answers: {practice_answers}")

    client = get_openai_client()
    if not client:
        print(f" [EVALUATION] No OpenAI client - using fallback evaluation")
        # Fallback to simple keyword-based evaluation
        return evaluate_practice_answers_fallback(practice_answers, practice_questions)

    try:
        print(f" [EVALUATION] Using OpenAI evaluation")
        # Prepare the evaluation prompt
        print(f" [EVALUATION] Building answers_text with enumerate:")
        answers_parts = []
        for i, q in enumerate(practice_questions):
            answer = practice_answers.get(i, 'No answer')
            part = f"Question {i+1}: {q}\nAnswer: {answer}\n"
            answers_parts.append(part)
            print(f"   - i={i}, Question {i+1}, Answer key={i}, Answer value='{answer}'")
        
        answers_text = "\n".join(answers_parts)
        print(f" [EVALUATION] Final answers_text: {answers_text}")

        prompt = f"""
        You are an expert educator evaluating student answers for database and computer science topics.
        
        Evaluate the following practice answers for the topic: {topic}
        
        {answers_text}
        
        IMPORTANT RULES:
        - If the answer shows correct understanding → mark TRUE
        - Do NOT penalize for short answers
        - Accept concise answers
        - Accept paraphrased answers
        - Even partially correct answers → mark TRUE
        - Focus on concept correctness, NOT length or wording
        
        For each answer, provide detailed evaluation:
        1. Check if the answer is correct (true/false)
        2. Provide constructive feedback explaining why the answer is correct or incorrect
        3. Suggest improvements for incorrect answers
        
        Return your response as a JSON object with the following structure:
        {{
          "evaluations": [
            {{
              "question_number": 1,
              "correct": true/false,
              "feedback": "Detailed feedback here"
            }},
            {{
              "question_number": 2,
              "correct": true/false,
              "feedback": "Detailed feedback here"
            }}
          ]
                {{
                    "question_number": 1,
                    "correct": true/false,
                    "feedback": "Specific, educational feedback for this answer"
                }},
                {{
                    "question_number": 2,
                    "correct": true/false,
                    "feedback": "Specific, educational feedback for this answer"
                }}
            ]
        }}
        
        Example feedback for wrong answers:
        - "You mentioned that normalization organizes data, but missed the key point about reducing redundancy. Try to include both concepts."
        - "Good start! You identified the purpose, but explain how it improves data integrity."
        
        Example feedback for correct answers:
        - "Excellent! You correctly explained both the purpose (organizing data) and benefit (reducing redundancy)."
        - "Perfect answer! You covered all the key aspects of database normalization."
        """

        # Log OpenAI API request details
        print(f"🤖 [OPENAI API] REQUEST DETAILS:")
        print(f"   - Model: gpt-3.5-turbo")
        print(f"   - Temperature: 0.3")
        print(f"   - Max Tokens: 1000")
        print(f"   - Topic: {topic}")
        print(f"   - Number of Answers: {len(practice_answers)}")
        print(f"   - Number of Questions: {len(practice_questions)}")
        print(f"   - Prompt Length: {len(prompt)} characters")
        
        # Show truncated prompt for debugging
        prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
        print(f"   - Prompt Preview: {prompt_preview}")

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an IT Teacher evaluating student answers. Provide constructive, detailed feedback that helps students learn."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        # Log OpenAI API response details
        ai_response = response.choices[0].message.content
        print(f"📤 [OPENAI API] RESPONSE DETAILS:")
        print(f"   - Response Length: {len(ai_response)} characters")
        print(f"   - Response Preview: {ai_response[:300]}...")
        print(f"   - Full Response: {ai_response}")

        result_text = response.choices[0].message.content.strip()
        print(f" [EVALUATION] OpenAI response: {result_text}")

        # Try to parse JSON response (model often wraps JSON in markdown fences)
        cleaned = _strip_code_fence_json(result_text)
        try:
            result = json.loads(cleaned)
            print(f" [EVALUATION] Parsed JSON result: {result}")
            
            # Process OpenAI result directly without mixing with fallback
            evaluations = result.get("evaluations", [])
            question_results = []
            correct_count = 0
            
            for i, eval_item in enumerate(evaluations):
                is_correct = bool(eval_item.get("correct", False))
                if is_correct:
                    correct_count += 1
                    
                question_results.append({
                    "question_number": eval_item.get("question_number", i + 1),
                    "correct": is_correct,
                    "feedback": eval_item.get("feedback", "No feedback provided")
                })
            
            return {
                "correct_answers": correct_count,
                "total_answers": len(practice_questions),
                "question_results": question_results,
                "overall_score": round((correct_count / len(practice_questions)) * 100, 1) if len(practice_questions) > 0 else 0
            }
            
        except json.JSONDecodeError as e:
            print(f" [EVALUATION] JSON parsing failed: {e}")
            print(f" [EVALUATION] Falling back to keyword evaluation")
            # Fallback if JSON parsing fails
            return evaluate_practice_answers_fallback(practice_answers, practice_questions)

    except Exception as e:
        print(f" [EVALUATION] OpenAI evaluation failed: {e}")
        print(f" [EVALUATION] Falling back to keyword evaluation")
        return evaluate_practice_answers_fallback(practice_answers, practice_questions)


def evaluate_practice_answers_fallback(practice_answers: Dict[int, str], practice_questions: List[str]) -> Dict[str, Any]:
    """Fallback evaluation using simple keyword matching."""
    correct_count = 0
    total_count = len(practice_questions)
    question_results = []

    for i, question in enumerate(practice_questions):
        answer = practice_answers.get(i, "").lower().strip()
        is_correct = False
        feedback = ""

        if not answer:
            feedback = "No answer provided."
        else:
            # Simple keyword-based evaluation
            question_lower = question.lower()

            # Check for basic understanding based on question type
            if "normalization" in question_lower and "what is" in question_lower:
                expected_concepts = ["organizing", "data", "redundancy", "integrity", "structure", "tables"]
                if any(concept in answer for concept in expected_concepts):
                    is_correct = True
                    correct_count += 1
                    feedback = "Good! You understand that normalization involves organizing data to reduce redundancy and improve integrity."
                else:
                    feedback = "Try to mention key concepts like organizing data, reducing redundancy, or improving data integrity."
            elif any(keyword in question_lower for keyword in ["what is", "define", "explain"]):
                # Look for definition-like answers
                if any(word in answer for word in ["is", "are", "refers to", "means", "defined as"]):
                    is_correct = True
                    correct_count += 1
                    feedback = "Good definition provided."
                else:
                    feedback = "Try to include definition words like 'is', 'means', or 'refers to'."
            elif any(keyword in question_lower for keyword in ["how", "process", "steps"]):
                # Look for process-related answers
                if any(word in answer for word in ["first", "then", "next", "finally", "step"]):
                    is_correct = True
                    correct_count += 1
                    feedback = "Good explanation of the process."
                else:
                    feedback = "Include sequence words like 'first', 'then', 'next' to describe the process."
            elif any(keyword in question_lower for keyword in ["why", "reason", "because"]):
                # Look for explanation answers
                if any(word in answer for word in ["because", "due to", "reason", "causes"]):
                    is_correct = True
                    correct_count += 1
                    feedback = "Good explanation of reasons."
                else:
                    feedback = "Include reasoning words like 'because', 'due to', or 'causes'."
            else:
                # Default: if answer has substantial content, consider it partially correct
                if len(answer.split()) > 5:
                    is_correct = True
                    correct_count += 1
                    feedback = "Good attempt with substantial content."
                else:
                    feedback = "Provide more detailed explanation."

        question_results.append({
            "question_number": i + 1,
            "correct": is_correct,
            "feedback": feedback
        })

    return {
        "correct_answers": correct_count,
        "total_answers": total_count,
        "detailed_feedback": "Basic keyword-based evaluation completed",
        "overall_score": round((correct_count / total_count) * 100, 1) if total_count > 0 else 0,
        "question_results": question_results
    }


# ═══════════════════════════════════════════════════════════════
#  Webhook-based Practice Question System
# ═══════════════════════════════════════════════════════════════

async def fetch_questions_from_webhook(difficulty: str) -> List[Dict[str, Any]]:
    """
    Fetch practice questions from external webhook API.
    
    Args:
        difficulty: The difficulty level (easy, medium, hard)
        
    Returns:
        List of questions with id and text
        
    Example webhook response:
        [
            {"id": 1, "question": "What is a superkey?"},
            {"id": 2, "question": "Define primary key"}
        ]
    """
    webhook_url = f"{settings.N8N_WEBHOOK_URL}/questions"

    print(f"🔍 [DEBUG] Webhook URL: {webhook_url}")
    print(f"🔍 [DEBUG] Difficulty requested: {difficulty}")
    print(f"🔍 [DEBUG] N8N_WEBHOOK_URL from settings: {settings.N8N_WEBHOOK_URL}")

    try:
        print(f"🌐 [WEBHOOK] Fetching questions for difficulty: {difficulty}")
        print(f"🌐 [WEBHOOK] Making request to: {webhook_url}")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                webhook_url,
                params={"difficulty": difficulty}
            )

            print(f"🔍 [DEBUG] Response status code: {response.status_code}")
            print(f"🔍 [DEBUG] Response headers: {dict(response.headers)}")

            if response.status_code == 200:
                questions_data = response.json()
                print(f"🔍 [DEBUG] Raw response data: {questions_data}")

                # Validate webhook response format
                if not isinstance(questions_data, list):
                    print(f"❌ [WEBHOOK] Invalid response format - expected list, got {type(questions_data)}")
                    print(f"🔍 [DEBUG] Falling back to empty list due to invalid format")
                    return []

                # Validate each question has required fields
                valid_questions = []
                for i, q in enumerate(questions_data):
                    if isinstance(q, dict) and "id" in q and "question" in q:
                        valid_questions.append({
                            "id": q["id"],
                            "question": q["question"]
                        })
                    else:
                        print(f"⚠️ [WEBHOOK] Invalid question format at index {i}: {q}")

                print(f"✅ [WEBHOOK] Successfully fetched {len(valid_questions)} questions from N8N")
                print(f"🔍 [DEBUG] Validated questions: {valid_questions}")
                print(f"🔍 [DATA_SOURCE] Using N8N WEBHOOK API")
                return valid_questions

            else:
                print(f"❌ [WEBHOOK] HTTP error {response.status_code}: {response.text}")
                print(f"🔍 [DEBUG] Failed to get questions from N8N - will return empty list")
                print(f"🔍 [DATA_SOURCE] N8N WEBHOOK FAILED - No fallback implemented")
                return []

    except Exception as e:
        print(f"❌ [WEBHOOK] Failed to fetch questions: {e}")
        print(f"🔍 [DEBUG] Exception occurred: {type(e).__name__}: {e}")
        print(f"🔍 [DATA_SOURCE] N8N WEBHOOK ERROR - No fallback implemented")
        return []


async def evaluate_answer_strict(question: str, student_answer: str) -> Dict[str, Any]:
    """
    Evaluate student answer using strict AI examiner.
    
    Args:
        question: The question text
        student_answer: The student's answer
        
    Returns:
        {"result": 1 or 0, "correct_answer": "only if wrong"}
        
    Output format is strict JSON only with no explanations.
    """
    client = get_openai_client()
    if not client:
        print(f"❌ [EVALUATION] No OpenAI client - fallback to 0")
        return {"result": 0, "correct_answer": "Unable to evaluate - OpenAI not available"}

    try:
        print(f"🤖 [EVALUATION] Evaluating answer for question: {question[:50]}...")

        prompt = f"""
You are a helpful and fair academic evaluator.

Evaluate the student answer based on understanding, NOT strict wording.

IMPORTANT RULES:
- If the answer shows correct concept → score = 1
- If the answer is completely wrong → score = 0
- Accept short answers if concept is correct
- Accept paraphrased answers
- DO NOT expect textbook definitions
- Even if answer is partially correct → give score = 1

Examples:
Q: What is trivial functional dependency?
A: RHS subset of LHS → score = 1

Q: What is a primary key?
A: uniquely identifies record → score = 1

Return ONLY JSON. No explanation.

Input:
Question: {question}
Student Answer: {student_answer}

Output:
{{
  "score": 1,
  "correct_answer": null
}}

OR

{{
  "score": 0,
  "correct_answer": "correct answer here"
}}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a fair academic evaluator. Return only valid JSON, no explanations."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=200
        )

        result_text = response.choices[0].message.content.strip()
        print(f"🤖 [EVALUATION] AI response: {result_text}")

        # Extract JSON from AI response (handles extra text/formatting)
        parsed = _extract_json_object(result_text)

        if parsed is None:
            return {"result": 0, "correct_answer": "Invalid JSON"}

        score = int(parsed.get("score", 0))

        result = {"result": 1 if score == 1 else 0}

        if result["result"] == 0:
            result["correct_answer"] = parsed.get("correct_answer", "Incorrect answer")

        print("🧠 FINAL SCORE:", score)
        return result

    except Exception as e:
        print(f"❌ [EVALUATION] Evaluation failed: {e}")
        return {"result": 0, "correct_answer": "Evaluation error"}


def decide_next_step(correct_count: int, current_difficulty: str) -> Dict[str, Any]:
    """
    Decide the next step based on quiz performance.
    
    Args:
        correct_count: Number of correct answers
        current_difficulty: Current difficulty level
        
    Returns:
        {
            "action": "next_difficulty" or "retry_same_difficulty",
            "next_difficulty": new difficulty level,
            "message": explanation of the decision
        }
    """
    print(f"🎯 [DECISION] Evaluating performance: {correct_count} correct at {current_difficulty}")

    if correct_count >= 3:
        # Move to next difficulty
        if current_difficulty == "easy":
            next_difficulty = "medium"
        elif current_difficulty == "medium":
            next_difficulty = "hard"
        else:
            next_difficulty = "hard"  # Stay at hard if already there

        message = f"Excellent! {correct_count} correct answers. Moving to {next_difficulty} level."

        return {
            "action": "next_difficulty",
            "next_difficulty": next_difficulty,
            "message": message
        }
    else:
        # Retry same difficulty with new questions
        message = f"You got {correct_count} correct answers. Need 3+ to advance. Try again with new questions."

        return {
            "action": "retry_same_difficulty",
            "next_difficulty": current_difficulty,
            "message": message
        }


async def run_webhook_quiz_round(difficulty: str, student_answers: Dict[int, str]) -> Dict[str, Any]:
    """
    Run a complete quiz round with webhook questions and strict evaluation.
    
    Args:
        difficulty: The difficulty level for this round
        student_answers: Dictionary mapping question_id to student_answer
        
    Returns:
        {
            "difficulty": difficulty,
            "questions_asked": number,
            "correct_count": number,
            "wrong_count": number,
            "results": [evaluation results for each question],
            "next_step": decision result
        }
    """
    print(f"🎯 [WEBHOOK_QUIZ] Starting quiz round at difficulty: {difficulty}")

    # Fetch 5 questions from webhook
    questions = await fetch_questions_from_webhook(difficulty)

    if len(questions) == 0:
        print(f"❌ [WEBHOOK_QUIZ] No questions available")
        return {
            "difficulty": difficulty,
            "questions_asked": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "results": [],
            "next_step": {"action": "retry_same_difficulty", "next_difficulty": difficulty, "message": "No questions available from webhook"}
        }

    # Limit to 5 questions
    questions = questions[:5]

    correct_count = 0
    wrong_count = 0
    results = []

    for i, question_data in enumerate(questions):
        question_id = question_data["id"]
        question_text = question_data["question"]
        student_answer = student_answers.get(question_id, "")

        print(f"❓ [WEBHOOK_QUIZ] Question {i+1}/{len(questions)}: {question_text}")
        print(f"📝 [WEBHOOK_QUIZ] Student answer: {student_answer}")

        # Evaluate answer using strict AI
        evaluation = await evaluate_answer_strict(question_text, student_answer)

        print(f"🔢 [WEBHOOK_QUIZ] Evaluation result for question {i+1}: {evaluation}")

        if evaluation["result"] == 1:
            correct_count += 1
            print(f"✅ [WEBHOOK_QUIZ] Question {i+1} CORRECT. Total correct: {correct_count}")
        else:
            wrong_count += 1
            print(f"❌ [WEBHOOK_QUIZ] Question {i+1} WRONG. Total wrong: {wrong_count}")

        results.append({
            "question_id": question_id,
            "question": question_text,
            "student_answer": student_answer,
            "evaluation": evaluation
        })

    print(f"🔢 [WEBHOOK_QUIZ] FINAL COUNTS - Correct: {correct_count}, Wrong: {wrong_count}")

    # Decide next step
    next_step = decide_next_step(correct_count, difficulty)

    return {
        "difficulty": difficulty,
        "questions_asked": len(questions),
        "correct_count": correct_count,
        "wrong_count": wrong_count,
        "results": results,
        "next_step": next_step
    }


def predict_next_difficulty(original_feedback: Dict[str, Any], correct_answers: int, total_answers: int) -> str:
    """Predict the next difficulty level based on performance."""
    current_difficulty = original_feedback.get("difficulty", "easy")
    score_percentage = (correct_answers / total_answers) * 100 if total_answers > 0 else 0

    # Get the original score to consider overall performance
    original_score = original_feedback.get("score", 0)

    # Combined performance metric
    combined_score = (score_percentage + original_score) / 2

    if combined_score >= 90:
        # Excellent performance - jump to hard
        return "hard"
    elif combined_score >= 75:
        # Good performance - move to medium if not already there
        if current_difficulty == "easy":
            return "medium"
        elif current_difficulty == "medium":
            return "hard"
        else:
            return "hard"
    elif combined_score >= 60:
        # Average performance - stay at current or slight increase
        if current_difficulty == "easy":
            return "medium"
        else:
            return current_difficulty
    else:
        # Below average - stay at current level or move down
        if current_difficulty == "hard":
            return "medium"
        else:
            return current_difficulty
