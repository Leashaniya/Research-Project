from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from app.services.evaluation_service import (
    generate_practice_questions,
    evaluate_practice_answers,
    call_n8n_webhook,
    predict_next_difficulty,
    fetch_questions_from_webhook,
    evaluate_answer_strict,
    decide_next_step,
    run_webhook_quiz_round
)

router = APIRouter(tags=["practice"])


class PracticeQuestionsRequest(BaseModel):
    topic: str


class PracticeQuestionsResponse(BaseModel):
    topic: str
    questions: List[str]


class PracticeEvaluationRequest(BaseModel):
    practice_answers: Dict[int, str]
    practice_questions: List[str]
    original_feedback: Dict[str, Any]
    topic: str


class PracticeEvaluationResponse(BaseModel):
    passed: bool
    correct_answers: int
    total_answers: int
    feedback: str
    next_difficulty: Optional[str] = None
    additional_questions: Optional[List[str]] = None
    # Required by FeedbackPanel: per-question `correct` is dropped if not declared here.
    question_results: List[Dict[str, Any]] = Field(default_factory=list)


@router.post("/practice", response_model=PracticeQuestionsResponse)
async def generate_practice_questions_endpoint(body: PracticeQuestionsRequest):
    """Generate practice questions based on a topic."""
    if not body.topic or not body.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")
    
    questions = generate_practice_questions(body.topic)
    
    if not questions:
        raise HTTPException(status_code=404, detail="No questions could be generated for this topic")
    
    return {
        "topic": body.topic.strip(),
        "questions": questions
    }


@router.post("/practice/evaluate", response_model=PracticeEvaluationResponse)
async def evaluate_practice_answers_endpoint(
    body: PracticeEvaluationRequest,
    x_session_id: Optional[str] = Header(None)
):
    """Evaluate practice answers and determine next steps."""
    
    print(f"🔍 [BACKEND] Received practice evaluation request for topic: {body.topic}")
    print(f"📝 [BACKEND] Number of answers: {len(body.practice_answers)}")
    print(f"❓ [BACKEND] Number of questions: {len(body.practice_questions)}")
    
    # Evaluate the answers
    evaluation = await evaluate_practice_answers(
        body.practice_answers,
        body.practice_questions,
        body.topic
    )
    
    print(f"📊 [BACKEND] Evaluation result: {evaluation}")
    
    correct_count = evaluation["correct_answers"]
    total_count = evaluation["total_answers"]
    passed = correct_count >= 3
    
    print(f"✅ [BACKEND] Student {'PASSED' if passed else 'FAILED'}: {correct_count}/{total_count}")
    
    additional_questions = None
    next_difficulty = None
    
    if passed:
        # Student passed - predict next difficulty
        next_difficulty = predict_next_difficulty(
            body.original_feedback,
            correct_count,
            total_count
        )
        print(f"📈 [BACKEND] Predicted next difficulty: {next_difficulty}")
        feedback = f"Excellent work! You got {correct_count} out of {total_count} correct. Moving to {next_difficulty} level."
    else:
        # Student failed - trigger webhook for additional practice
        print(f"📚 [BACKEND] Student failed - triggering webhook for additional questions...")
        
        webhook_payload = {
            "topic": body.topic,
            "original_question": body.original_feedback.get("question", ""),
            "original_answer": "",  # This would need to be passed if needed
            "evaluation_result": evaluation,
            "practice_performance": {
                "correct_answers": correct_count,
                "total_answers": total_count,
                "answers": body.practice_answers
            }
        }
        
        print(f"🌐 [BACKEND] Webhook payload: {webhook_payload}")
        
        # Call n8n webhook for additional questions
        webhook_questions = await call_n8n_webhook(webhook_payload)
        
        if webhook_questions:
            additional_questions = webhook_questions
            print(f"✅ [BACKEND] Received {len(webhook_questions)} additional questions from n8n")
        else:
            # Fallback to local generation
            additional_questions = generate_practice_questions(f"{body.topic} - additional practice")
            print(f"🔄 [BACKEND] Using fallback local generation: {len(additional_questions)} questions")
        
        feedback = f"You got {correct_count} out of {total_count} correct. Keep practicing with these additional questions to improve your understanding."
    
    result = {
        "passed": passed,
        "correct_answers": correct_count,
        "total_answers": total_count,
        "feedback": feedback,
        "next_difficulty": next_difficulty,
        "additional_questions": additional_questions,
        "question_results": evaluation.get("question_results", [])
    }
    
    print(f"🎯 [BACKEND] Final response: {result}")
    return result


# ═══════════════════════════════════════════════════════════════
#  Webhook-based Practice Question System
# ═══════════════════════════════════════════════════════════════

class WebhookQuestionsRequest(BaseModel):
    difficulty: str  # easy, medium, hard

class WebhookQuestionsResponse(BaseModel):
    difficulty: str
    questions: List[Dict[str, Any]]  # [{"id": 1, "question": "What is..."}]

class StrictEvaluationRequest(BaseModel):
    question: str
    student_answer: str

class StrictEvaluationResponse(BaseModel):
    result: int  # 0 or 1
    correct_answer: Optional[str] = None

class WebhookQuizRoundRequest(BaseModel):
    difficulty: str
    student_answers: Dict[int, str]  # question_id -> answer

class WebhookQuizRoundResponse(BaseModel):
    difficulty: str
    questions_asked: int
    correct_count: int
    wrong_count: int
    results: List[Dict[str, Any]]
    next_step: Dict[str, Any]


@router.get("/webhook/questions", response_model=WebhookQuestionsResponse)
async def get_webhook_questions(difficulty: str):
    """Fetch questions from external webhook API."""
    print(f"🌐 [BACKEND] Fetching webhook questions for difficulty: {difficulty}")
    
    questions = await fetch_questions_from_webhook(difficulty)
    
    return WebhookQuestionsResponse(
        difficulty=difficulty,
        questions=questions
    )


@router.post("/webhook/evaluate", response_model=StrictEvaluationResponse)
async def evaluate_answer_strict_endpoint(body: StrictEvaluationRequest):
    """Evaluate a single answer using strict AI examiner."""
    print(f"🤖 [BACKEND] Strict evaluation for question: {body.question[:50]}...")
    
    result = await evaluate_answer_strict(body.question, body.student_answer)
    
    return StrictEvaluationResponse(**result)


@router.post("/webhook/quiz-round", response_model=WebhookQuizRoundResponse)
async def run_webhook_quiz_round_endpoint(body: WebhookQuizRoundRequest):
    """Run a complete quiz round with webhook questions and strict evaluation."""
    print(f"🎯 [BACKEND] Starting webhook quiz round at difficulty: {body.difficulty}")
    
    result = await run_webhook_quiz_round(body.difficulty, body.student_answers)
    
    return WebhookQuizRoundResponse(**result)
