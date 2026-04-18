from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api.routes.sessions import get_session
from app.core.config import settings
from app.services.evaluation_service import (
    evaluate_answer, detect_topic, get_practice_questions_with_fallback,
    evaluate_practice_answers, predict_next_difficulty
)
from app.services.rl_engine import rl_engine
from app.services.logging_service import log_attempt

router = APIRouter(tags=["answers"])


class SubmitAnswerRequest(BaseModel):
    answer: Optional[str] = None  # For individual submission
    answers: Optional[Dict[int, str]] = None  # For batch submission
    questions: Optional[List[str]] = None  # For batch submission
    question: Optional[str] = None  # For individual submission
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    batch_mode: bool = False  # Flag to determine submission mode


class BatchSubmitRequest(BaseModel):
    answers: Dict[int, str]  # question_id -> answer
    questions: List[str]
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    additional_round: Optional[bool] = False  # Flag to indicate this is additional practice round


class BatchSubmitResponse(BaseModel):
    session_id: str
    status: str  # "PASSED" or "FAILED"
    correct_answers: int
    total_answers: int
    feedback: str
    next_difficulty: Optional[str] = None
    next_questions: Optional[List[Dict[str, Any]]] = None
    additional_questions: Optional[List[str]] = None
    retry_available: bool = False
    webhook_used: bool = False
    question_results: List[Dict[str, Any]] = []
    evaluation_result: Dict[str, Any] = {}


@router.post("/api/answers/submit")
async def submit_answer(
    body: SubmitAnswerRequest,
    x_session_id: Optional[str] = Header(None),
):
    """Submit answers - supports both individual and batch modes."""
    sid, sess = get_session(x_session_id)

    # Check if batch mode is requested
    if body.batch_mode and body.answers and body.questions:
        # BATCH MODE - Evaluate all answers together
        return await _handle_batch_submission(body, sid, sess)
    else:
        # INDIVIDUAL MODE - Evaluate single answer
        return await _handle_individual_submission(body, sid, sess)


async def _handle_batch_submission(body: SubmitAnswerRequest, sid: str, sess: dict):
    """Handle batch submission of multiple answers."""
    difficulty = body.difficulty or sess["difficulty"]
    topic = body.topic or detect_topic(body.questions[0]) if body.questions else "General"

    print(f"🔍 [BATCH EVAL] Starting batch evaluation for {len(body.answers)} answers")
    print(f"📚 [BATCH EVAL] Topic: {topic}, Difficulty: {difficulty}")
    
    # Log input payload for debugging
    print(f"📥 [BATCH EVAL] INPUT PAYLOAD:")
    print(f"   - Session ID: {sid}")
    print(f"   - Answers Type: {type(body.answers)}")
    print(f"   - Answers: {body.answers}")
    print(f"   - Answers Keys: {list(body.answers.keys()) if body.answers else 'None'}")
    print(f"   - Answers Values: {list(body.answers.values()) if body.answers else 'None'}")
    print(f"   - Questions Type: {type(body.questions)}")
    print(f"   - Questions: {body.questions}")
    print(f"   - Questions Length: {len(body.questions) if body.questions else 0}")
    print(f"   - Topic: {topic}")
    print(f"   - Difficulty: {difficulty}")
    print(f"   - Batch Mode: {body.batch_mode}")

    # Evaluate all answers together
    print(f"🤖 [BATCH EVAL] Calling evaluate_practice_answers...")
    evaluation = await evaluate_practice_answers(
        body.answers,
        body.questions,
        topic
    )
    
    # Log AI evaluation output for debugging
    print(f"📤 [BATCH EVAL] AI EVALUATION OUTPUT:")
    print(f"   - Evaluation Result: {evaluation}")
    print(f"   - Correct Answers: {evaluation.get('correct_answers', 'N/A')}")
    print(f"   - Total Answers: {evaluation.get('total_answers', 'N/A')}")
    print(f"   - Question Results: {evaluation.get('question_results', 'N/A')}")

    correct_count = evaluation["correct_answers"]
    total_count = evaluation["total_answers"]
    passed = correct_count >= 3

    print(f"✅ [BATCH EVAL] Result: {correct_count}/{total_count} correct. PASSED: {passed}")

    # Initialize batch evaluation tracking in session
    if "batch_evaluations" not in sess:
        sess["batch_evaluations"] = []
    
    # Store batch evaluation result
    batch_result = {
        "topic": topic,
        "difficulty": difficulty,
        "total_answers": total_count,
        "correct_answers": correct_count,
        "passed": passed,
        "evaluation": evaluation,
        "timestamp": sess["attempt"] + 1
    }
    sess["batch_evaluations"].append(batch_result)

    # Update session stats for batch
    sess["attempt"] += 1
    avg_score = (correct_count / total_count) * 100 if total_count > 0 else 0
    sess["total_score"] += avg_score
    sess["score_history"].append({
        "attempt": sess["attempt"],
        "score": avg_score,
        "difficulty": difficulty,
        "topic": topic,
        "reward": 1.0 if passed else -0.5,
        "type": "batch"
    })

    additional_questions = None
    next_difficulty = None
    next_questions = None
    webhook_used = False
    retry_available = True
    webhook_payload = {}

    if passed:
        # Student passed - predict next difficulty and generate next questions
        print(f"🎉 [BATCH EVAL] Student PASSED - predicting next difficulty")
        
        next_difficulty = predict_next_difficulty(
            {"difficulty": difficulty, "score": avg_score},
            correct_count,
            total_count
        )
        
        print(f"📈 [BATCH EVAL] Predicted next difficulty: {next_difficulty}")
        
        # Generate next set of questions at predicted difficulty
        from app.services.evaluation_service import generate_practice_questions
        next_questions = [
            {
                "question": q,
                "difficulty": next_difficulty,
                "topic": topic,
                "bloom_level": "Apply"
            }
            for q in generate_practice_questions(f"{topic} - {next_difficulty}")[:3]
        ]
        
        feedback = f"Excellent! You got {correct_count} out of {total_count} answers correct. Moving to {next_difficulty} level."
        
        # Update session difficulty
        sess["difficulty"] = next_difficulty
        
    else:
        # Student failed - trigger webhook for additional practice
        print(f"📚 [BATCH EVAL] Student FAILED - triggering webhook for additional questions...")
        
        webhook_payload = {
            "is_correct": False,
            "question_text": body.questions[0] if body.questions else "",
            "topic": topic,
            "feedback": {
                "weaknesses": f"Student got {total_count - correct_count} out of {total_count} answers wrong"
            },
            "recommendation": f"Review {topic} concepts and try again"
        }
        
        # Call n8n webhook for additional questions
        webhook_questions = await get_practice_questions_with_fallback(webhook_payload)
        
        if webhook_questions:
            additional_questions = webhook_questions
            webhook_used = True
            print(f"✅ [BATCH EVAL] Received {len(webhook_questions)} additional questions from n8n")
        else:
            # Fallback to local generation
            from app.services.evaluation_service import generate_practice_questions
            additional_questions = generate_practice_questions(f"{topic} - additional practice")
            print(f"🔄 [BATCH EVAL] Using fallback local generation: {len(additional_questions)} questions")
        
        feedback = f"You got {correct_count} out of {total_count} correct. Keep practicing with these additional questions to improve your understanding."

    # Create evaluation result for response
    evaluation_result = {
        "is_correct": passed,
        "feedback": feedback,
        "topic": topic,
        "recommendation": webhook_payload.get("recommendation", ""),
        "correct_answers": correct_count,
        "total_answers": total_count,
        "passed": passed
    }

    # Store last batch result in session
    sess["last_result"] = {
        "type": "batch",
        "questions": body.questions,
        "answers": body.answers,
        "correct_answers": correct_count,
        "total_answers": total_count,
        "passed": passed,
        "feedback": feedback,
        "difficulty": difficulty,
        "topic": topic,
        "attempt": sess["attempt"],
        "next_difficulty": next_difficulty,
        "additional_questions": additional_questions,
        "next_questions": next_questions
    }

    # Log batch attempt
    log_attempt(sess["attempt"], topic, difficulty, {
        "concept_count": 0,
        "mistakes": total_count - correct_count,
        "answer_length": sum(len(body.answers.get(i, "").split()) for i in range(len(body.questions)))
    }, 1.0 if passed else -0.5, avg_score)

    # Prepare final response
    final_response = {
        "session_id": sid,
        "status": "PASSED" if passed else "FAILED",
        "correct_answers": correct_count,
        "total_answers": total_count,
        "score": avg_score,
        "is_correct": passed,
        "reward": 1.0 if passed else -0.5,
        "feedback": feedback,
        "next_difficulty": next_difficulty,
        "next_questions": next_questions,
        "additional_questions": additional_questions,
        "retry_available": retry_available,
        "webhook_used": webhook_used,
        "question_results": evaluation.get("question_results", []),
        "evaluation_result": evaluation_result,
        "attempt": sess["attempt"],
        "topic": topic,
        "difficulty": difficulty,
        "batch_mode": True
    }
    
    # Log final response for debugging
    print(f"📤 [BATCH EVAL] FINAL RESPONSE TO FRONTEND:")
    print(f"   - Session ID: {final_response['session_id']}")
    print(f"   - Status: {final_response['status']}")
    print(f"   - Correct Answers: {final_response['correct_answers']}")
    print(f"   - Total Answers: {final_response['total_answers']}")
    print(f"   - Score: {final_response['score']}")
    print(f"   - Is Correct: {final_response['is_correct']}")
    print(f"   - Reward: {final_response['reward']}")
    print(f"   - Feedback: {final_response['feedback']}")
    print(f"   - Next Difficulty: {final_response['next_difficulty']}")
    print(f"   - Question Results Count: {len(final_response['question_results'])}")
    print(f"   - Batch Mode: {final_response['batch_mode']}")
    
    return final_response


async def _handle_individual_submission(body: SubmitAnswerRequest, sid: str, sess: dict):
    """Handle individual submission of single answer."""
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
        "type": "individual"
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
        "type": "individual",
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
        "evaluation_result": evaluation_result,
        "batch_mode": False
    }


@router.post("/api/answers/batch-submit", response_model=BatchSubmitResponse)
async def batch_submit_answers(
    body: BatchSubmitRequest,
    x_session_id: Optional[str] = Header(None),
):
    """Submit and evaluate multiple student answers in one request."""
    sid, sess = get_session(x_session_id)

    if not body.questions or len(body.questions) == 0:
        raise HTTPException(status_code=400, detail="No questions provided")
    
    if not body.answers or len(body.answers) == 0:
        raise HTTPException(status_code=400, detail="No answers provided")
    
    topic = body.topic or "General"
    difficulty = body.difficulty or "easy"
    
    print(f"🔍 [BATCH EVAL] Starting batch evaluation for {len(body.questions)} questions on topic: {topic}")
    if body.additional_round:
        print(f"� [BATCH EVAL] This is an ADDITIONAL practice round")
    
    # Evaluate all answers together
    evaluation = await evaluate_practice_answers(
        body.answers,
        body.questions,
        topic
    )

    correct_count = evaluation["correct_answers"]
    total_count = evaluation["total_answers"]
    passed = correct_count >= 3

    print(f"✅ [BATCH EVAL] Result: {correct_count}/{total_count} correct. PASSED: {passed}")

    # Initialize batch evaluation tracking in session
    if "batch_evaluations" not in sess:
        sess["batch_evaluations"] = []
    
    # Store batch evaluation result
    batch_result = {
        "topic": topic,
        "difficulty": difficulty,
        "total_answers": total_count,
        "correct_answers": correct_count,
        "passed": passed,
        "evaluation": evaluation,
        "timestamp": sess["attempt"] + 1
    }
    sess["batch_evaluations"].append(batch_result)

    # Update session stats for batch
    sess["attempt"] += 1
    sess["total_score"] += correct_count
    sess["average_score"] = sess["total_score"] / sess["attempt"]

    # Prepare response variables
    additional_questions = None
    next_questions = None
    next_difficulty = None
    webhook_used = False
    retry_available = True
    webhook_payload = {}

    if passed:
        # Student passed - predict next difficulty and generate next questions
        print(f"🎉 [BATCH EVAL] Student PASSED - predicting next difficulty")
        
        # Predict next difficulty based on performance
        next_difficulty = predict_next_difficulty(
            {
                "question": body.questions[0] if body.questions else "",
                "student_answer": body.answers.get(0, ""),
                "is_correct": True,
                "feedback": {
                    "weaknesses": "None identified",
                    "strengths": "Good understanding"
                },
                "recommendation": "Continue to next level"
            },
            correct_count,
            total_count
        )
        
        # Generate next set of questions at predicted difficulty
        from app.services.evaluation_service import generate_practice_questions
        next_questions = [
            {
                "question": q,
                "difficulty": next_difficulty,
                "topic": topic,
                "bloom_level": "Apply"
            }
            for q in generate_practice_questions(f"{topic} - {next_difficulty}")[:3]
        ]
        
        feedback = f"Excellent! You got {correct_count} out of {total_count} answers correct. Moving to {next_difficulty} level."
        
        # Update session difficulty
        sess["difficulty"] = next_difficulty
        
    else:
        # Student failed
        if body.additional_round:
            # This is an additional practice round - don't generate more questions, just provide feedback
            print(f"📚 [BATCH EVAL] Student FAILED additional practice round - providing feedback only")
            feedback = f"You got {correct_count} out of {total_count} correct in the additional practice. Continue studying and practicing to improve your understanding."
        else:
            # This is the first round - generate additional practice questions
            print(f"📚 [BATCH EVAL] Student FAILED - generating 5 additional practice questions...")
            
            webhook_payload = {
                "is_correct": False,
                "question_text": body.questions[0] if body.questions else "",
                "topic": topic,
                "feedback": {
                    "weaknesses": f"Student got {total_count - correct_count} out of {total_count} answers wrong"
                },
                "recommendation": f"Review {topic} concepts and try again",
                "question_count": 5  # Explicitly request 5 questions
            }
            
            # Call n8n webhook for additional questions
            webhook_questions = await get_practice_questions_with_fallback(webhook_payload)
            
            if webhook_questions and len(webhook_questions) >= 5:
                # Take first 5 questions if more are returned
                additional_questions = webhook_questions[:5]
                webhook_used = True
                print(f"✅ [BATCH EVAL] Received {len(webhook_questions)} additional questions from n8n, using first 5")
            else:
                # Fallback to local generation - ensure exactly 5 questions
                from app.services.evaluation_service import generate_practice_questions
                additional_questions = generate_practice_questions(f"{topic} - additional practice")
                # Ensure we have exactly 5 questions
                while len(additional_questions) < 5:
                    more_questions = generate_practice_questions(f"{topic} - more practice")
                    additional_questions.extend(more_questions)
                additional_questions = additional_questions[:5]
                print(f"🔄 [BATCH EVAL] Using fallback local generation: generated {len(additional_questions)} questions")
            
            feedback = f"You got {correct_count} out of {total_count} correct. Here are 5 more practice questions to help you improve."

    # Create evaluation result for response
    evaluation_result = {
        "is_correct": passed,
        "feedback": feedback,
        "topic": topic,
        "recommendation": webhook_payload.get("recommendation", ""),
        "correct_answers": correct_count,
        "total_answers": total_count,
        "passed": passed
    }

    # Store last batch result in session
    sess["last_result"] = {
        "type": "batch",
        "questions": body.questions,
        "answers": body.answers,
        "correct_answers": correct_count,
        "total_answers": total_count,
        "passed": passed,
        "feedback": feedback,
        "difficulty": difficulty,
        "topic": topic,
        "attempt": sess["attempt"],
        "next_difficulty": next_difficulty,
        "additional_questions": additional_questions,
        "next_questions": next_questions
    }

    # Log batch attempt
    log_attempt(sess["attempt"], topic, difficulty, {
        "concept_count": 0,
        "mistakes": total_count - correct_count,
        "answer_length": sum(len(body.answers.get(i, "").split()) for i in range(len(body.questions)))
    }, 1.0 if passed else -0.5, avg_score)

    return {
        "session_id": sid,
        "status": "PASSED" if passed else "FAILED",
        "correct_answers": correct_count,
        "total_answers": total_count,
        "feedback": feedback,
        "next_difficulty": next_difficulty,
        "next_questions": next_questions,
        "additional_questions": additional_questions,
        "retry_available": retry_available,
        "webhook_used": webhook_used,
        "question_results": evaluation.get("question_results", []),
        "evaluation_result": evaluation_result
    }
