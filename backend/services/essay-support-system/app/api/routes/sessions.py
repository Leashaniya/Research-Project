import uuid
from typing import Dict, Optional, Any

from fastapi import APIRouter, Header

from app.services.question_bank import question_bank

router = APIRouter(tags=["sessions"])


# ═══════════════════════════════════════════════════════════════
#  In-memory session store  (mirrors Flask globals in app.py)
# ═══════════════════════════════════════════════════════════════

sessions: Dict[str, Dict[str, Any]] = {}


def _new_session() -> dict:
    return {
        "difficulty": "easy",
        "score_history": [],
        "attempt": 0,
        "total_score": 0,
        "current_question": None,
    }


def get_session(session_id: Optional[str]) -> tuple:
    """Return (session_id, session_data). Create if missing."""
    if session_id and session_id in sessions:
        return session_id, sessions[session_id]
    sid = session_id or str(uuid.uuid4())
    sessions[sid] = _new_session()
    return sid, sessions[sid]


# ═══════════════════════════════════════════════════════════════
#  Pydantic request models
# ═══════════════════════════════════════════════════════════════

from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    difficulty: Optional[str] = "easy"


# ═══════════════════════════════════════════════════════════════
#  Routes
# ═══════════════════════════════════════════════════════════════

@router.post("/api/sessions/start")
async def start_session(
    body: StartSessionRequest,
    x_session_id: Optional[str] = Header(None),
):
    sid, sess = get_session(None)           # always fresh
    sess["difficulty"] = body.difficulty or "easy"
    return {
        "session_id": sid,
        "difficulty": sess["difficulty"],
        "questions_available": question_bank.count,
    }


@router.post("/api/sessions/reset")
async def reset_session(
    x_session_id: Optional[str] = Header(None),
):
    sid, sess = get_session(x_session_id)
    # Preserve the difficulty setting when resetting
    preserved_difficulty = sess.get("difficulty", "easy")
    sessions[sid] = _new_session()
    sessions[sid]["difficulty"] = preserved_difficulty
    return {"session_id": sid, "message": "Session reset", "difficulty": preserved_difficulty}
