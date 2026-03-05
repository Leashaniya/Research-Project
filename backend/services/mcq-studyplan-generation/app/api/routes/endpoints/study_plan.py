"""Study plan and adaptive plan endpoints."""
import os
import sys
from pathlib import Path
from datetime import datetime

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import state
from app.services.mcq_service import generate_study_plan_pdf, generate_adaptive_outputs

router = APIRouter()


class StudyPlanRequest(BaseModel):
    total_hours: float = 20.0
    study_days: int = 7


class AdaptivePlanRequest(BaseModel):
    quiz_results: dict
    total_hours: float = 20.0
    study_days: int = 7
    alpha: float = 0.5
    max_increase: float = 0.30
    max_decrease: float = 0.15


@router.post("/generate", include_in_schema=True)
async def generate_study_plan(req: StudyPlanRequest):
    """Generate study plan from percentage distribution."""
    if state.PERCENTAGE_DF.empty:
        raise HTTPException(status_code=400, detail="Please run analysis first")


    from analysis_utils import generate_study_plan_based_on_percentage

    study_plan_df, daily_schedule_df = generate_study_plan_based_on_percentage(
        state.PERCENTAGE_DF, req.total_hours, req.study_days
    )
    state.STUDY_PLAN_DF = study_plan_df
    state.DAILY_SCHEDULE_DF = daily_schedule_df
    state.TOTAL_HOURS = req.total_hours
    state.STUDY_DAYS = req.study_days

    plan_list = []
    for _, row in study_plan_df.iterrows():
        pct = row.get("Question_Percentage", 0)
        if isinstance(pct, str):
            pct = float(pct.replace("%", "")) if pct else 0
        else:
            pct = float(pct) if pct else 0
        plan_list.append({
            "priority": int(row["Priority"]),
            "lecture": row["Lecture"],
            "focus_intensity": row["Focus_Intensity"],
            "recommended_hours": float(row["Recommended_Hours"]),
            "questions": int(row.get("Question_Count", 0)),
            "percentage": pct,
        })
    daily_schedule = daily_schedule_df.to_dict("records") if not daily_schedule_df.empty else []
    return {
        "plan": plan_list,
        "daily_schedule": daily_schedule,
        "total_hours": req.total_hours,
        "study_days": req.study_days,
    }


@router.get("/download-pdf", include_in_schema=True)
async def download_study_plan_pdf(total_hours: float = 20, study_days: int = 7):
    """Download study plan as PDF."""
    if state.STUDY_PLAN_DF.empty or state.DAILY_SCHEDULE_DF.empty:
        raise HTTPException(status_code=400, detail="No study plan available")


    study_plan_df = state.STUDY_PLAN_DF.copy()
    daily_schedule_df = state.DAILY_SCHEDULE_DF.copy()
    if "Question_Percentage" in study_plan_df.columns and study_plan_df["Question_Percentage"].dtype == "object":
        study_plan_df["Question_Percentage"] = study_plan_df["Question_Percentage"].astype(str).str.replace("%", "").astype(float)

    pdf_buffer = generate_study_plan_pdf(study_plan_df, daily_schedule_df, total_hours, study_days)
    return Response(
        content=pdf_buffer.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=study_plan_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"},
    )


@router.post("/adaptive/generate", include_in_schema=True)
async def generate_adaptive_plan_internal(req: AdaptivePlanRequest):
    """Generate adaptive study plan from quiz results."""
    if state.STUDY_PLAN_DF.empty:
        raise HTTPException(status_code=400, detail="Generate baseline study plan first")
    if not req.quiz_results:
        raise HTTPException(status_code=400, detail="Quiz results required")


    from analysis_utils import generate_adaptive_study_plan

    adaptive_plan_df, adaptive_daily_df = generate_adaptive_study_plan(
        state.STUDY_PLAN_DF,
        req.quiz_results,
        req.total_hours,
        req.study_days,
        alpha=req.alpha,
        max_increase=req.max_increase,
        max_decrease=req.max_decrease,
    )
    if adaptive_plan_df.empty:
        raise HTTPException(status_code=400, detail="Failed to generate adaptive plan")

    state.ADAPTIVE_PLAN_DF = adaptive_plan_df
    state.ADAPTIVE_DAILY_DF = adaptive_daily_df
    state.ADAPTIVE_PARAMS = {
        "total_hours": req.total_hours,
        "study_days": req.study_days,
        "alpha": req.alpha,
        "max_increase": req.max_increase,
        "max_decrease": req.max_decrease,
    }
    generate_adaptive_outputs(adaptive_plan_df, state.STUDY_PLAN_DF)

    adaptive_plan = []
    for _, row in adaptive_plan_df.iterrows():
        adaptive_plan.append({
            "Priority": row["Priority"],
            "Lecture": row["Lecture"],
            "Baseline_Hours": float(row["Baseline_Hours"]),
            "Adaptive_Hours": float(row["Adaptive_Hours"]),
            "Delta_Hours": float(row["Delta_Hours"]),
            "Quiz_Accuracy": row["Quiz_Accuracy"],
            "Mastery_Gap": row["Mastery_Gap"],
            "Focus_Intensity": row["Focus_Intensity"],
        })
    adaptive_daily = adaptive_daily_df.to_dict("records") if not adaptive_daily_df.empty else []
    return {
        "success": True,
        "adaptive_plan": adaptive_plan,
        "adaptive_daily": adaptive_daily,
        "params": state.ADAPTIVE_PARAMS,
    }


# Separate router for /api/adaptive-plan/generate (mcqApi expects this path)
router_adaptive = APIRouter()
router_adaptive.add_api_route("/generate", generate_adaptive_plan_internal, methods=["POST"])
