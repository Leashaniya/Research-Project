"""Evaluation metrics endpoints."""
import sys
from pathlib import Path

from fastapi import APIRouter

from app.services import state

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from evaluation_metrics import calculate_and_save_evaluation_metrics

router = APIRouter()


@router.get("/evaluation", include_in_schema=True)
async def get_evaluation_metrics():
    """Return recommendation/adaptive evaluation metrics."""
    metrics = calculate_and_save_evaluation_metrics(
        percentage_df=state.PERCENTAGE_DF,
        adaptive_plan_df=state.ADAPTIVE_PLAN_DF if state.ADAPTIVE_PLAN_DF is not None else state.STUDY_PLAN_DF,
    )
    return metrics
