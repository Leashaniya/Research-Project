from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.api.routes.sessions import get_session
from app.services.question_bank import question_bank
from app.services.bloom_classifier import classify_bloom_level

router = APIRouter(tags=["questions"])


class GetQuestionRequest(BaseModel):
    difficulty: Optional[str] = None


@router.post("/api/questions/next")
async def get_question(
    body: GetQuestionRequest,
    x_session_id: Optional[str] = Header(None),
):
    sid, sess = get_session(x_session_id)
    difficulty = body.difficulty or sess["difficulty"]

    q = question_bank.get_question(difficulty)
    if not q:
        raise HTTPException(status_code=404, detail="No questions available")

    sess["current_question"] = q
    bloom = classify_bloom_level(q["question"])

    return {
        "session_id": sid,
        "question": q["question"],
        "difficulty": q["difficulty"],
        "topic": q.get("topic", "General"),
        "source": q.get("source", ""),
        "page": q.get("page"),
        "bloom_level": bloom,
    }


@router.get("/api/pdfs/check")
async def check_pdfs():
    pdf_list = question_bank.get_pdf_list()
    return {
        "pdfs": pdf_list,
        "count": len(pdf_list),
        "questions_loaded": question_bank.count,
    }
