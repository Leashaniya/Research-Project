"""Quiz and priority questions endpoints."""
import os
import sys
from pathlib import Path

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import state
from evaluation_utils import evaluate_answers, prepare_quiz_questions

router = APIRouter()  # for /api/priority-questions
router_quiz = APIRouter()  # for /api/quiz


class QuizSubmitRequest(BaseModel):
    answers: dict
    correct_answers: dict


@router.get("", include_in_schema=True)
async def get_priority_questions():
    """Get priority questions for quiz."""
    if state.PERCENTAGE_DF.empty or not state.LECTURE_DATA:
        raise HTTPException(status_code=400, detail="Please run analysis first")

    from quiz_extraction import extract_questions_from_top_priorities

    extracted = extract_questions_from_top_priorities(
        state.LECTURE_DATA,
        state.PERCENTAGE_DF,
        num_priorities=4,
        total_questions=28,
    )
    quiz_questions = prepare_quiz_questions(extracted)

    result = []
    for q in quiz_questions:
        opts = q.get("options", [])
        if isinstance(opts, str):
            opts = [o.strip() for o in opts.split(" | ") if o.strip()]
        result.append({
            "id": q["question_id"],
            "question": q["question_text"],
            "options": opts,
            "answer": q.get("correct_answer", ""),
            "lecture": q.get("lecture", ""),
            "lecture_title": q.get("lecture_title", ""),
            "priority": q.get("priority", 0),
            "question_number": q.get("question_number", 0),
        })
    return result


@router_quiz.post("/submit", include_in_schema=True)
async def submit_quiz(req: QuizSubmitRequest):
    """Submit quiz answers and get evaluation results."""
    if not req.answers or not req.correct_answers:
        raise HTTPException(status_code=400, detail="Missing answers or correct_answers")


    results = evaluate_answers(req.answers, req.correct_answers)


    lecture_accuracy = {}
    for lecture, perf in results.get("topic_wise", {}).items():
        acc = perf.get("accuracy", 0)
        val = acc / 100.0 if acc > 1 else acc
        lecture_accuracy[lecture] = val
        if not lecture.endswith(".pdf"):
            lecture_accuracy[f"{lecture}.pdf"] = val
    results["accuracy_by_lecture"] = lecture_accuracy
    acc_val = results.get("accuracy", 0)
    results["overall_accuracy"] = acc_val / 100.0 if acc_val > 1 else acc_val
    return results
