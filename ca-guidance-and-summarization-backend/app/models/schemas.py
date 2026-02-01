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


# ============ Flashcard Feedback Schemas ============

class FlashcardItem(BaseModel):
    """Single flashcard with question and answer"""
    id: str  # Unique ID for tracking feedback
    question: str
    answer: str


class SaveFlashcardSetRequest(BaseModel):
    """Request to save a flashcard set"""
    topic: str
    flashcards: dict  # Bloom levels -> list of flashcards


class FlashcardFeedbackRequest(BaseModel):
    """Request to submit feedback for a specific flashcard"""
    flashcard_set_id: str  # ID of the flashcard set
    flashcard_id: str  # ID of the specific flashcard
    bloom_level: str  # remember, understand, apply, analyze, evaluate, create
    rating: str  # "thumbs_up", "thumbs_down", "1"-"5" for star rating
    feedback_type: Optional[str] = None  # "add_examples", "simplify", "more_detail", "other"
    comment: Optional[str] = None  # Free-form feedback text
    session_id: Optional[str] = None


class FlashcardUpdateRequest(BaseModel):
    """Request to update a flashcard based on feedback"""
    flashcard_set_id: str
    flashcard_id: str
    bloom_level: str
    feedback_id: str  # Reference to the feedback that triggered this update


class FlashcardSetResponse(BaseModel):
    """Response containing a full set of flashcards with IDs"""
    _id: str
    topic: str
    user_email: str
    flashcards: dict  # Bloom levels -> list of FlashcardItem
    version: int = 1
    created_at: datetime
    updated_at: Optional[datetime] = None


class FlashcardFeedbackResponse(BaseModel):
    """Response after submitting feedback"""
    feedback_id: str
    flashcard_set_id: str
    flashcard_id: str
    bloom_level: str
    rating: str
    feedback_type: Optional[str] = None
    comment: Optional[str] = None
    created_at: datetime


class UpdatedFlashcardResponse(BaseModel):
    """Response containing the updated flashcard after improvement"""
    flashcard_id: str
    bloom_level: str
    original_question: str
    original_answer: str
    updated_question: str
    updated_answer: str
    improvement_notes: str
    version: int

