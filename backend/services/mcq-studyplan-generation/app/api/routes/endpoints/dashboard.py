"""Dashboard and analysis endpoints."""
import os
import sys
from pathlib import Path

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter
from app.services import state
from app.services.mcq_service import run_analysis

router = APIRouter()


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=True)
async def health():
    """Health check."""
    return {"status": "ok", "service": "mcq-study-plan"}


@router.get("/stats", include_in_schema=True)
async def get_stats():
    """Dashboard stats for React."""
    pct_df = state.PERCENTAGE_DF
    total_lectures = len(state.LECTURE_DATA)
    total_questions = len(state.MCQ_DF) if not state.MCQ_DF.empty else 0
    high_priority = len(pct_df[pct_df["Percentage_of_Total"] > 10]) if not pct_df.empty else 0
    avg_per_lecture = round(total_questions / total_lectures, 1) if total_lectures > 0 else 0
    return {
        "total_lectures": total_lectures,
        "total_questions": total_questions,
        "total_topics": total_lectures,
        "avg_questions_per_lecture": avg_per_lecture,
        "high_priority_lectures": high_priority,
        "study_completion_percentage": 0,
        "processed": state.PROCESSED,
    }


@router.post("/analyze", include_in_schema=True)
async def analyze():
    """Run analysis on lecture materials."""
    success, message = run_analysis()
    if not success:
        return {"success": False, "message": message}
    pct_df = state.PERCENTAGE_DF
    total_lectures = len(state.LECTURE_DATA)
    total_questions = len(state.MCQ_DF) if not state.MCQ_DF.empty else 0
    high_priority = len(pct_df[pct_df["Percentage_of_Total"] > 10]) if not pct_df.empty else 0
    avg_per_lecture = round(total_questions / total_lectures, 1) if total_lectures > 0 else 0
    return {
        "success": True,
        "message": message,
        "stats": {
            "total_lectures": total_lectures,
            "total_questions": total_questions,
            "total_topics": total_lectures,
            "avg_questions_per_lecture": avg_per_lecture,
            "high_priority_lectures": high_priority,
            "study_completion_percentage": 0,
            "processed": True,
        },
        "question_distribution_count": len(pct_df) if not pct_df.empty else 0,
        "total_lectures": total_lectures,
        "total_questions": total_questions,
        "percentage_df": pct_df.to_dict("records") if not pct_df.empty else [],
    }


@router.get("/lecture-distribution", include_in_schema=True)
async def list_lecture_distribution():
    """Lecture distribution data for charts."""
    if state.PERCENTAGE_DF.empty:
        return []
    return state.PERCENTAGE_DF.to_dict("records")
