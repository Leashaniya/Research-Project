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
    feedback_type: Optional[str] = None  # "add_examples", "simplify", "more_detail", "clarify"
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


# ============ Flashcard Feedback Schemas ============

class SaveFlashcardSetRequest(BaseModel):
    """Request to save a flashcard set"""
    topic: str
    flashcards: dict  # Bloom levels -> list of flashcards


class FlashcardFeedbackRequest(BaseModel):
    """Request to submit feedback for a specific flashcard"""
    flashcard_set_id: str
    flashcard_id: str
    bloom_level: str  # remember, understand, apply, analyze, evaluate, create
    rating: str  # "thumbs_up", "thumbs_down"
    feedback_type: Optional[str] = None  # "add_examples", "simplify", "more_detail", "clarify"
    comment: Optional[str] = None
    session_id: Optional[str] = None


class FlashcardUpdateRequest(BaseModel):
    """Request to update a flashcard based on feedback"""
    flashcard_set_id: str
    flashcard_id: str
    bloom_level: str
    feedback_id: str


# ============ Guidance Reinforcement Schemas ============

class GuidanceFeedbackRequest(BaseModel):
    """Request to submit feedback for CA guidance"""
    guidance_id: str
    rating: str  # "helpful" or "not_helpful"
    confused_concept: Optional[str] = None
    comment: Optional[str] = None
    feedback_type: Optional[str] = None  # add_more_links, new_deadline_event, doubt_on_questions, simplify_language
    deadline_text: Optional[str] = None  # when feedback_type is new_deadline_event
    session_id: Optional[str] = None


class ReinforceGuidanceRequest(BaseModel):
    """Request to generate reinforced guidance from feedback"""
    guidance_id: str  # base guidance_id
    feedback_id: Optional[str] = None
    force: bool = False
    session_id: Optional[str] = None


class GuidancePdfRequest(BaseModel):
    report_content: str
    images: List[str] = []
    title: Optional[str] = None
    file_name: Optional[str] = None

