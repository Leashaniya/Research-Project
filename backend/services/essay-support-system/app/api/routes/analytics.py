from typing import Dict, Optional

from fastapi import APIRouter, Header

from app.api.routes.sessions import get_session
from app.services.rl_engine import rl_engine
from app.services.logging_service import get_attempt_history

router = APIRouter(tags=["analytics"])


@router.get("/api/analytics/overview")
async def analytics_overview(x_session_id: Optional[str] = Header(None)):
    all_history = get_attempt_history()

    # Calculate aggregations
    topics: Dict[str, int] = {}
    difficulties: Dict[str, int] = {}
    scores: list = []
    difficulty_over_time: list = []

    for row in all_history:
        t = row.get("topic", "General")
        d = row.get("difficulty", "medium")
        try:
            s = float(row.get("score", 0))
        except ValueError:
            s = 0
        topics[t] = topics.get(t, 0) + 1
        difficulties[d] = difficulties.get(d, 0) + 1
        scores.append(s)
        difficulty_over_time.append(d)

    avg = round(sum(scores) / len(scores), 1) if scores else 0

    return {
        "total_attempts": len(all_history),
        "average_score": avg,
        "topics": topics,
        "difficulties": difficulties,
        "scores": scores,
        "difficulty_over_time": difficulty_over_time,
        "rl_policy": rl_engine.get_dict(),
    }
