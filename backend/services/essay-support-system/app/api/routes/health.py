from fastapi import APIRouter
from app.services.question_bank import question_bank
from app.services.rl_engine import rl_engine

router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "questions_loaded": question_bank.count,
        "rl_states": len(rl_engine.policy),
    }
