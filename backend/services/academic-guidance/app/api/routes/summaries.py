import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user
from app.models.schemas import UserInfo
from app.ca_guidance.tools.tts_tool import text_to_speech_wav

logger = logging.getLogger(__name__)


router = APIRouter(tags=["summaries"])


class ReinforceFromFeedbackRequest(BaseModel):
    topic: str
    force: bool = True
    # Optional scoping to ensure reinforcement is tied to current base + session
    summary_id: str | None = None
    session_id: str | None = None


@router.post("/summaries/reinforce")
async def reinforce_summary_from_feedback(
    request: ReinforceFromFeedbackRequest,
    user: UserInfo = Depends(get_current_user),
):
    """
    Regenerate a reinforced summary for a topic using the latest submitted feedback.

    Contract:
      POST /summaries/reinforce
      { "topic": "<topic>", "force": true }
    """
    topic = (request.topic or "").strip()
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty.",
        )

    try:
        from bson.objectid import ObjectId
        from app.services.summary_reinforcement_service import SummaryReinforcementService

        service = SummaryReinforcementService()

        # If force=False, allow returning cached reinforced summary when it exists
        if not request.force:
            existing = service.get_latest_summary(topic, prefer_reinforced=True, user_email=user.email)
            if existing and existing.get("summary_type") == "reinforced":
                # Prefer GridFS URL when audio is stored there
                audio_url = existing.get("audio_url") or (
                    f"/protected/summaries/{existing['_id']}/audio" if existing.get("audio_file_id") else None
                )
                return {
                    "summary": existing["summary_text"],
                    "images": existing.get("images", []),
                    "topic": topic,
                    "audio_url": audio_url,
                    "summary_id": existing["_id"],
                    "summary_type": "reinforced",
                    "created_at": existing.get("created_at").isoformat() if existing.get("created_at") else None,
                    "audio_duration_seconds": existing.get("audio_duration_seconds"),
                    "from_cache": True,
                }

        # Base summary is immutable for this operation (never overwritten)
        base_doc = None
        if request.summary_id:
            try:
                base_doc = service.summaries_collection.find_one({"_id": ObjectId(request.summary_id)})
            except Exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid summary_id format: {request.summary_id}",
                )
            if base_doc and base_doc.get("summary_type") != "base":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="summary_id must reference a base summary.",
                )

            # Ensure summary topic matches request.topic (avoid cross-topic leakage)
            if base_doc and str(base_doc.get("topic", "")).lower().strip() != topic.lower().strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="summary_id does not match the provided topic.",
                )

        if not base_doc:
            topic_lower = topic.lower().strip()
            base_doc = service.summaries_collection.find_one(
                {
                    "topic": topic_lower,
                    "summary_type": "base",
                    "$or": [{"user_email": user.email}, {"user_email": {"$exists": False}}],
                }
            )

        if not base_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No base summary found for topic '{topic}'. Create a base summary first.",
            )

        latest_feedback = service.get_latest_feedback_for_summary(
            str(base_doc["_id"]), user_email=user.email, session_id=request.session_id
        ) or service.get_latest_feedback_for_topic(topic, user_email=user.email, session_id=request.session_id)
        if not latest_feedback:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No feedback found for this topic. Submit feedback first.",
            )

        feedback = {
            "rating": latest_feedback.get("rating", "not_helpful"),
            "confused_concept": latest_feedback.get("confused_concept"),
            "comment": latest_feedback.get("comment"),
        }

        reinforced_text = service.generate_reinforced_summary(
            topic=topic,
            base_summary_text=base_doc["summary_text"],
            feedback=feedback,
        )

        # Generate audio for reinforced summary (optional; skipped if Piper not configured)
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(reinforced_text)
            if audio_path:
                audio_url = f"/audio/{Path(audio_path).name}"
                logger.info(f"✅ Audio generated for reinforced summary: {audio_url}")
            else:
                logger.info("TTS skipped (Piper not configured)")
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)

        images = base_doc.get("images", [])

        reinforced_id = service.store_reinforced_summary(
            topic=topic,
            summary_text=reinforced_text,
            base_summary_id=str(base_doc["_id"]),
            feedback_id=str(latest_feedback.get("_id")) if latest_feedback.get("_id") else None,
            images=images,
            audio_url=audio_url,
            user_email=user.email,
            session_id=request.session_id,
        )

        # Persist audio blob + duration metadata (optional)
        audio_duration_seconds = None
        if audio_path and audio_url and reinforced_id:
            attach = service.attach_audio_to_summary(
                summary_id=reinforced_id,
                topic=topic,
                summary_type="reinforced",
                audio_path=audio_path,
                user_email=user.email,
                session_id=request.session_id,
            )
            audio_duration_seconds = attach.get("audio_duration_seconds")
            if attach.get("audio_file_id"):
                audio_url = f"/protected/summaries/{reinforced_id}/audio"
                service.summaries_collection.update_one(
                    {"_id": ObjectId(reinforced_id)},
                    {"$set": {"audio_url": audio_url}},
                )

        stored = service.summaries_collection.find_one({"_id": ObjectId(reinforced_id)})
        # Use GridFS URL when we have audio in DB
        effective_audio_url = (
            f"/protected/summaries/{reinforced_id}/audio" if stored and stored.get("audio_file_id") else audio_url
        )

        return {
            "summary": reinforced_text,
            "images": images,
            "topic": topic,
            "audio_url": effective_audio_url,
            "summary_id": reinforced_id,
            "summary_type": "reinforced",
            "base_summary_id": str(base_doc["_id"]),
            "feedback_id": str(latest_feedback.get("_id")) if latest_feedback.get("_id") else None,
            "created_at": stored.get("created_at").isoformat() if stored and stored.get("created_at") else None,
            "audio_duration_seconds": stored.get("audio_duration_seconds") if stored else audio_duration_seconds,
            "from_cache": False,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reinforced summary from feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reinforced summary: {e}",
        )

