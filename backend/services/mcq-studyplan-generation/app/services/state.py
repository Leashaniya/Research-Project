"""In-memory state for MCQ Study Plan (replaces Flask app.config)."""
import pandas as pd
from typing import List, Dict, Any, Optional

# Mutable state - shared across requests
LECTURE_DATA: List[Dict[str, Any]] = []
MCQ_DF: pd.DataFrame = pd.DataFrame()
PERCENTAGE_DF: pd.DataFrame = pd.DataFrame()
ALL_TOPICS: List[Dict[str, Any]] = []
STUDY_PLAN_DF: pd.DataFrame = pd.DataFrame()
DAILY_SCHEDULE_DF: pd.DataFrame = pd.DataFrame()
ADAPTIVE_PLAN_DF: Optional[pd.DataFrame] = None
ADAPTIVE_DAILY_DF: Optional[pd.DataFrame] = None
ADAPTIVE_PARAMS: Dict[str, Any] = {}
TOTAL_HOURS: float = 20.0
STUDY_DAYS: int = 7
PROCESSED: bool = False
DETAILED_REPORT: Optional[pd.DataFrame] = None
