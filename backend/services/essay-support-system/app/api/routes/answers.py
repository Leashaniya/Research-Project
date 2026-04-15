from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api.routes.sessions import get_session
from app.core.config import settings
from app.services.evaluation_service import (
    evaluate_answer, detect_topic, get_practice_questions_with_fallback
)
from app.services.rl_engine import rl_engine
from app.services.logging_service import log_attempt

router = APIRouter(tags=["answers"])


class SubmitAnswerRequest(BaseModel):
    answer: str
    question: Optional[str] = None
    difficulty: Optional[str] = None


@router.post("/api/answers/submit")
async def submit_answer(
    body: SubmitAnswerRequest,
    x_session_id: Optional[str] = Header(None),
):
    sid, sess = get_session(x_session_id)

    current = sess.get("current_question")
    question_text = body.question or (current["question"] if current else "")
    difficulty = body.difficulty or sess["difficulty"]

    if not question_text:
        raise HTTPException(status_code=400, detail="No active question")

    # Evaluate
    result = evaluate_answer(body.answer, question_text, difficulty)
    score = float(result.get("score", 50))
    behaviour = result.get("behaviour", {
        "concept_count": 0, "mistakes": 0, "answer_length": len(body.answer.split()),
    })
    is_correct = score >= settings.CORRECTNESS_THRESHOLD

    # Reward signal (mirrors app.py)
    if score >= 80:
        reward = 1.0
    elif score >= 50:
        reward = 0.5
    else:
        reward = -0.5

    # RL update
    topic = detect_topic(question_text)
    action_key = f"{difficulty}_{topic}"
    rl_engine.update(action_key, reward)

    # Update next difficulty (mirrors app.py adaptive logic)
    levels = ["easy", "medium", "hard"]
    idx = levels.index(difficulty) if difficulty in levels else 1
    if reward > 0 and idx < 2:
        next_diff = levels[idx + 1]
    elif reward < 0 and idx > 0:
        next_diff = levels[idx - 1]
    else:
        next_diff = difficulty

    sess["difficulty"] = next_diff
    sess["attempt"] += 1
    sess["total_score"] += score
    sess["score_history"].append({
        "attempt": sess["attempt"],
        "score": score,
        "difficulty": difficulty,
        "topic": topic,
        "reward": reward,
    })

    # Log to CSV
    log_attempt(sess["attempt"], topic, difficulty, behaviour, reward, score)

    # Create evaluation result for n8n
    evaluation_result = {
        "is_correct": is_correct,
        "feedback": result.get("feedback", {}).get("improvements", ""),
        "topic": result.get("topic", topic),
        "recommendation": result.get("recommendation", "")
    }
    
    # Get practice questions if answer is incorrect
    practice_questions = []
    if not is_correct:
        practice_questions = await get_practice_questions_with_fallback(evaluation_result)
    
    # Include practice questions in response
    evaluation_result["practice_questions"] = practice_questions
    
    # Store last result in session (useful for exports / history)
    sess["last_result"] = {
        "question": question_text,
        "student_answer": body.answer,
        "score": score,
        "is_correct": is_correct,
        "feedback": result.get("feedback", {}),
        "study_recommendations": result.get("study_recommendations", []),
        "difficulty": difficulty,
        "topic": topic,
        "attempt": sess["attempt"],
        "next_difficulty": next_diff,
        "practice_questions": practice_questions,
    }

    return {
        "session_id": sid,
        "question": question_text,
        "student_answer": body.answer,
        "score": score,
        "is_correct": is_correct,
        "reward": reward,
        "feedback": result.get("feedback", {}),
        "study_recommendations": result.get("study_recommendations", []),
        "recommendations": result.get("study_recommendations", []),
        "behaviour": behaviour,
        "next_difficulty": next_diff,
        "attempt": sess["attempt"],
        "topic": topic,
        "difficulty": difficulty,
        "validated": bool(result.get("_validated", False)),
        "fallback_used": bool(result.get("_fallback_used", False)),
        "practice_questions": practice_questions,
        "evaluation_result": evaluation_result  # For automation tools
    }
