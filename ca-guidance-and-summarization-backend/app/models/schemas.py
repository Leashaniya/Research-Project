from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class UserInfo(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None
    access_token: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo

class SummarizeRequest(BaseModel):
    topic: str
    force: bool = False  # If True, regenerate even if exists in DB


# Summary Reinforcement Schemas
class SummaryFeedbackRequest(BaseModel):
    topic: str
    summary_id: str
    rating: str  # "helpful" or "not_helpful"
    confused_concept: Optional[str] = None
    comment: Optional[str] = None
    session_id: Optional[str] = None


class ReinforceSummaryRequest(BaseModel):
    topic: str
    summary_id: str
    feedback_id: Optional[str] = None
    force: bool = False  # If True, regenerate even if exists in DB
    session_id: Optional[str] = None


class SummaryResponse(BaseModel):
    _id: str
    topic: str
    summary_text: str
    summary_type: str  # "base" or "reinforced"
    version: int
    images: List[str] = []
    audio_url: Optional[str] = None
    base_summary_id: Optional[str] = None
    feedback_id: Optional[str] = None
    created_at: datetime


class FeedbackResponse(BaseModel):
    _id: str
    topic: str
    summary_id: str
    rating: str
    confused_concept: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime

