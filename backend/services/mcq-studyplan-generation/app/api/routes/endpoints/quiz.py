"""Quiz and priority questions endpoints."""
import os
import sys
from pathlib import Path

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.services import state
from evaluation_utils import evaluate_answers, prepare_quiz_questions
from evaluation_metrics import calculate_and_save_evaluation_metrics
from graph_utils import build_pyvis_graph
from learning_state import update_learning_state_after_quiz
from graphrag.graph_retriever import (
    retrieve_recommended_mcqs,
    save_recommendations,
    record_attempted_question_ids,
)
from topic_labels import clean_topic_display_name

router = APIRouter()  # for /api/priority-questions
router_quiz = APIRouter()  # for /api/quiz
_LATEST_QUESTION_META: dict = {}


class QuizSubmitRequest(BaseModel):
    answers: dict
    correct_answers: dict


def _post_quiz_refresh(quiz_results: dict) -> None:
    """Run heavy post-quiz refresh work in background to avoid request timeouts."""
    recommendations_payload = None
    try:
        if not state.MCQ_DF.empty and state.LECTURE_DATA and state.ALL_TOPICS:
            from mcq_utils import compute_similarities

            sims, _ = compute_similarities(state.ALL_TOPICS, state.MCQ_DF)
            recs, meta = retrieve_recommended_mcqs(
                state.MCQ_DF,
                state.LECTURE_DATA,
                sims,
                quiz_state=quiz_results,
            )
            save_recommendations(recs, meta)

            graph_path = Path("outputs") / "graphrag_visualization.html"
            build_pyvis_graph(
                state.LECTURE_DATA,
                state.MCQ_DF,
                sims,
                str(graph_path),
                open_browser=False,
            )
            recommendations_payload = {"recommendations": recs, "meta": meta}
    except Exception as e:
        print(f"[quiz.submit] background GraphRAG refresh failed: {e}")

    try:
        graph_weak_topics = []
        if recommendations_payload and isinstance(recommendations_payload, dict):
            graph_weak_topics = (
                (recommendations_payload.get("meta") or {}).get("weak_topics_confirmed") or []
            )
        update_learning_state_after_quiz(
            quiz_results=quiz_results,
            graph_weak_topics=graph_weak_topics,
        )
    except Exception as e:
        print(f"[quiz.submit] background learning-state update failed: {e}")

    try:
        calculate_and_save_evaluation_metrics(
            quiz_results=quiz_results,
            recommendations_payload=recommendations_payload,
            percentage_df=state.PERCENTAGE_DF,
            adaptive_plan_df=state.ADAPTIVE_PLAN_DF if state.ADAPTIVE_PLAN_DF is not None else state.STUDY_PLAN_DF,
        )
    except Exception as e:
        print(f"[quiz.submit] background metrics computation failed: {e}")


@router.get("", include_in_schema=True)
async def get_priority_questions():
    """Get priority questions for quiz."""
    if state.PERCENTAGE_DF.empty or not state.LECTURE_DATA:
        raise HTTPException(status_code=400, detail="Please run analysis first")

    from quiz_extraction import extract_questions_from_top_priorities, NUM_TOP_PRIORITY_LECTURES

    extracted = extract_questions_from_top_priorities(
        state.LECTURE_DATA,
        state.PERCENTAGE_DF,
        num_priorities=NUM_TOP_PRIORITY_LECTURES,
        total_questions=44,
    )
    quiz_questions = prepare_quiz_questions(extracted)

    result = []
    global _LATEST_QUESTION_META
    _LATEST_QUESTION_META = {}
    for q in quiz_questions:
        opts = q.get("options", [])
        if isinstance(opts, str):
            opts = [o.strip() for o in opts.split(" | ") if o.strip()]
        qid = q["question_id"]
        topic_display = clean_topic_display_name(q.get("topic_name", "General"))
        _LATEST_QUESTION_META[qid] = {
            "lecture": q.get("lecture", ""),
            "topic_name": topic_display,
            "topic_confidence": q.get("topic_confidence", 0.0),
            "topic_match_method": q.get("topic_match_method", "fallback"),
        }
        result.append({
            "id": qid,
            "question": q["question_text"],
            "options": opts,
            "answer": q.get("correct_answer", ""),
            "lecture": q.get("lecture", ""),
            "lecture_title": q.get("lecture_title", ""),
            "priority": q.get("priority", 0),
            "question_number": q.get("question_number", 0),
            "topic_name": topic_display,
            "topic_confidence": q.get("topic_confidence", 0.0),
        })
    return result


@router_quiz.post("/submit", include_in_schema=True)
async def submit_quiz(req: QuizSubmitRequest, background_tasks: BackgroundTasks):
    """Submit quiz answers and get evaluation results."""
    if not req.answers or not req.correct_answers:
        raise HTTPException(status_code=400, detail="Missing answers or correct_answers")


    results = evaluate_answers(req.answers, req.correct_answers, _LATEST_QUESTION_META)


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
    try:
        record_attempted_question_ids(list(req.answers.keys()))
    except Exception:
        pass

    # Heavy GraphRAG refresh/metrics work runs in background to avoid 504 timeout.
    background_tasks.add_task(_post_quiz_refresh, dict(results))
    return results
