from typing import Optional

from fastapi import APIRouter, Header

from app.api.routes.sessions import get_session
from app.services.rl_engine import rl_engine
from app.services.logging_service import get_attempt_history

router = APIRouter(tags=["stats"])


@router.get("/api/stats")
async def get_stats(x_session_id: Optional[str] = Header(None)):
    sid, sess = get_session(x_session_id)
    attempts = sess["attempt"]
    avg_score = round(sess["total_score"] / attempts, 1) if attempts > 0 else 0

    return {
        "session_id": sid,
        "difficulty": sess["difficulty"],
        "attempts": attempts,
        "average_score": avg_score,
        "total_score": sess["total_score"],
        "score_history": sess["score_history"],
        "batch_evaluations": sess.get("batch_evaluations", []),
        "last_result": sess.get("last_result"),
        "rl_policy": rl_engine.get_dict(),
    }


@router.get("/api/history")
async def history():
    return {"history": get_attempt_history()}
