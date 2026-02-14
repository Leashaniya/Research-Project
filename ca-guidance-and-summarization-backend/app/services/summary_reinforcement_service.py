"""Service for summary reinforcement and MongoDB operations."""

import logging
from datetime import datetime
import wave
from pathlib import Path
from typing import Optional, Dict, Any, List
from bson.objectid import ObjectId
from pymongo.errors import DuplicateKeyError
from gridfs import GridFS

from app.core.database import get_database
from app.ca_guidance.tools.rag_tool import _get_rag_chain, _extract_context_text
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.core.config import settings

logger = logging.getLogger(__name__)


class SummaryReinforcementService:
    """Service for managing summaries and reinforcement learning."""
    
    def __init__(self):
        self.db = get_database()
        self.summaries_collection = self.db.summaries
        self.feedback_collection = self.db.summary_feedback
        # GridFS bucket for storing summary audio blobs
        self.audio_fs = GridFS(self.db, collection="summary_audio")
        
        # Create indexes
        self._create_indexes()
    
    def _create_indexes(self):
        """Create database indexes for efficient queries."""
        try:
            # Index for finding summaries by topic and type (not unique to avoid conflicts with existing data)
            # We'll enforce uniqueness in application logic instead
            self.summaries_collection.create_index(
                [("topic", 1), ("summary_type", 1)]
            )
            # Index for finding summaries by topic
            self.summaries_collection.create_index([("topic", 1)])
            # Index for feedback by summary_id
            self.feedback_collection.create_index([("summary_id", 1)])
            # Index for feedback by topic + created_at (latest feedback lookup)
            self.feedback_collection.create_index([("topic", 1), ("created_at", -1)])
            # Index for per-user topic summaries
            self.summaries_collection.create_index([("user_email", 1), ("topic", 1), ("summary_type", 1)])
            # Index for per-user, per-session feedback
            self.feedback_collection.create_index([("user_email", 1), ("session_id", 1), ("summary_id", 1), ("created_at", -1)])
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Failed to create indexes (may already exist): {e}")

    @staticmethod
    def _get_wav_duration_seconds(audio_path: str) -> Optional[float]:
        """Return WAV duration in seconds (or None if unknown)."""
        try:
            p = Path(audio_path)
            if not p.exists():
                return None
            with wave.open(str(p), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate() or 0
                if rate <= 0:
                    return None
                return float(frames) / float(rate)
        except Exception:
            return None

    def attach_audio_to_summary(
        self,
        *,
        summary_id: str,
        topic: str,
        summary_type: str,
        audio_path: str,
        content_type: str = "audio/wav",
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store audio blob in GridFS and attach metadata to the summary document.

        Returns:
            { "audio_file_id": str|None, "audio_duration_seconds": float|None }
        """
        try:
            p = Path(audio_path)
            if not p.exists():
                return {"audio_file_id": None, "audio_duration_seconds": None}

            duration_seconds = self._get_wav_duration_seconds(str(p))

            # Store in GridFS with metadata
            with p.open("rb") as f:
                file_id = self.audio_fs.put(
                    f,
                    filename=p.name,
                    contentType=content_type,
                    metadata={
                        "topic": topic.lower().strip(),
                        "summary_id": summary_id,
                        "summary_type": summary_type,
                        "duration_seconds": duration_seconds,
                        "user_email": user_email,
                        "session_id": session_id,
                        "created_at": datetime.utcnow(),
                    },
                )

            # Attach to summary doc
            self.summaries_collection.update_one(
                {"_id": ObjectId(summary_id)},
                {
                    "$set": {
                        "audio_file_id": file_id,
                        "audio_duration_seconds": duration_seconds,
                    }
                },
            )

            return {"audio_file_id": str(file_id), "audio_duration_seconds": duration_seconds}
        except Exception as e:
            logger.error(f"Failed to store/attach audio for summary {summary_id}: {e}", exc_info=True)
            return {"audio_file_id": None, "audio_duration_seconds": None}
    
    def store_base_summary(
        self,
        topic: str,
        summary_text: str,
        images: Optional[List[str]] = None,
        audio_url: Optional[str] = None,
        force: bool = False,
        user_email: Optional[str] = None,
    ) -> Optional[str]:
        """
        Store a base summary in MongoDB. Only ONE base summary per topic.
        
        Args:
            topic: The topic of the summary
            summary_text: The summary content
            images: Optional list of image paths
            audio_url: Optional audio URL
            force: If True, replace existing base summary. If False, skip if exists.
            
        Returns:
            The document ID as string if stored, None if skipped
        """
        try:
            topic_lower = topic.lower().strip()
            
            # Check if base summary already exists (prefer per-user, fall back to legacy docs)
            base_filter = {"topic": topic_lower, "summary_type": "base"}
            if user_email:
                base_filter = {
                    **base_filter,
                    "$or": [{"user_email": user_email}, {"user_email": {"$exists": False}}],
                }

            existing = self.summaries_collection.find_one(base_filter)
            
            summary_doc = {
                "topic": topic_lower,
                "summary_text": summary_text,
                "summary_type": "base",
                "user_email": user_email,
                "images": images or [],
                "audio_url": audio_url,
                "created_at": datetime.utcnow()
            }
            
            if existing:
                if force:
                    # Update existing when force=True
                    result = self.summaries_collection.update_one(
                        {"_id": existing["_id"]},
                        {"$set": summary_doc}
                    )
                    logger.info(f"Updated base summary for topic '{topic}' (id: {existing['_id']})")
                    return str(existing["_id"])
                else:
                    # Skip if exists and force=False
                    logger.info(f"Base summary already exists for topic '{topic}', skipping (use force=True to replace)")
                    return str(existing["_id"])
            else:
                # Insert new if doesn't exist
                result = self.summaries_collection.insert_one(summary_doc)
                logger.info(f"Stored base summary for topic '{topic}' (id: {result.inserted_id})")
                return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store base summary: {e}", exc_info=True)
            raise
    
    def store_reinforced_summary(
        self,
        topic: str,
        summary_text: str,
        base_summary_id: str,
        feedback_id: Optional[str] = None,
        images: Optional[List[str]] = None,
        audio_url: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Store or replace reinforced summary in MongoDB. Only ONE reinforced summary per topic.
        Uses upsert to replace existing if present.
        
        Args:
            topic: The topic of the summary
            summary_text: The reinforced summary content
            base_summary_id: ID of the base summary this reinforces
            feedback_id: Optional ID of the feedback that triggered reinforcement
            images: Optional list of image paths
            audio_url: Optional audio URL
            
        Returns:
            The document ID as string
        """
        try:
            topic_lower = topic.lower().strip()
            
            summary_doc = {
                "topic": topic_lower,
                "summary_text": summary_text,
                "summary_type": "reinforced",
                "user_email": user_email,
                "session_id": session_id,
                "base_summary_id": ObjectId(base_summary_id),
                "feedback_id": ObjectId(feedback_id) if feedback_id else None,
                "images": images or [],
                "audio_url": audio_url,
                "created_at": datetime.utcnow()
            }
            
            # Use upsert to replace existing or insert new
            reinforced_filter: Dict[str, Any] = {"topic": topic_lower, "summary_type": "reinforced"}
            if user_email:
                reinforced_filter["user_email"] = user_email

            result = self.summaries_collection.update_one(
                reinforced_filter,
                {"$set": summary_doc},
                upsert=True
            )
            
            # Get the document ID (either existing or newly inserted)
            if result.upserted_id:
                doc_id = str(result.upserted_id)
                logger.info(f"Stored new reinforced summary for topic '{topic}' (id: {doc_id})")
            else:
                # Document was updated, fetch it to get ID
                updated_doc = self.summaries_collection.find_one(
                    reinforced_filter
                )
                doc_id = str(updated_doc["_id"])
                logger.info(f"Updated reinforced summary for topic '{topic}' (id: {doc_id})")
            
            return doc_id
        except Exception as e:
            logger.error(f"Failed to store reinforced summary: {e}", exc_info=True)
            raise
    
    def get_latest_summary(self, topic: str, prefer_reinforced: bool = True, user_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get the summary for a topic (only one exists per type).
        
        Args:
            topic: The topic to search for
            prefer_reinforced: If True, prefer reinforced summaries over base summaries
            
        Returns:
            Summary document or None if not found
        """
        topic_lower = topic.lower().strip()
        
        if prefer_reinforced:
            # Try reinforced first
            if user_email:
                reinforced = self.summaries_collection.find_one(
                    {"topic": topic_lower, "summary_type": "reinforced", "user_email": user_email}
                )
                if not reinforced:
                    reinforced = self.summaries_collection.find_one(
                        {"topic": topic_lower, "summary_type": "reinforced", "user_email": {"$exists": False}}
                    )
            else:
                reinforced = self.summaries_collection.find_one(
                    {"topic": topic_lower, "summary_type": "reinforced"}
                )
            if reinforced:
                return self._format_summary_doc(reinforced)
        
        # Fall back to base summary
        if user_email:
            base = self.summaries_collection.find_one(
                {"topic": topic_lower, "summary_type": "base", "user_email": user_email}
            )
            if not base:
                base = self.summaries_collection.find_one(
                    {"topic": topic_lower, "summary_type": "base", "user_email": {"$exists": False}}
                )
        else:
            base = self.summaries_collection.find_one(
                {"topic": topic_lower, "summary_type": "base"}
            )
        
        return self._format_summary_doc(base) if base else None
    
    def get_all_summaries_for_topic(self, topic: str, user_email: Optional[str] = None) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Get both base and reinforced summaries for a topic.
        
        Args:
            topic: The topic to search for
            
        Returns:
            Dictionary with 'base' and 'reinforced' keys, each containing summary doc or None
        """
        topic_lower = topic.lower().strip()
        
        # Get base summary (only one exists)
        if user_email:
            base = self.summaries_collection.find_one(
                {"topic": topic_lower, "summary_type": "base", "user_email": user_email}
            )
            if not base:
                base = self.summaries_collection.find_one(
                    {"topic": topic_lower, "summary_type": "base", "user_email": {"$exists": False}}
                )
        else:
            base = self.summaries_collection.find_one(
                {"topic": topic_lower, "summary_type": "base"}
            )
        
        # Get reinforced summary (only one exists)
        if user_email:
            reinforced = self.summaries_collection.find_one(
                {"topic": topic_lower, "summary_type": "reinforced", "user_email": user_email}
            )
            if not reinforced:
                reinforced = self.summaries_collection.find_one(
                    {"topic": topic_lower, "summary_type": "reinforced", "user_email": {"$exists": False}}
                )
        else:
            reinforced = self.summaries_collection.find_one(
                {"topic": topic_lower, "summary_type": "reinforced"}
            )
        
        return {
            "base": self._format_summary_doc(base) if base else None,
            "reinforced": self._format_summary_doc(reinforced) if reinforced else None
        }
    
    def store_feedback(
        self,
        topic: str,
        summary_id: str,
        rating: str,
        confused_concept: Optional[str] = None,
        comment: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """
        Store user feedback for a summary.
        
        Args:
            topic: The topic of the summary
            summary_id: ID of the summary being rated
            rating: "helpful" or "not_helpful"
            confused_concept: Optional concept the user found confusing
            comment: Optional additional comment
            
        Returns:
            The inserted feedback document ID as string
        """
        if rating not in ["helpful", "not_helpful"]:
            raise ValueError("Rating must be 'helpful' or 'not_helpful'")
        
        try:
            feedback_doc = {
                "topic": topic.lower().strip(),
                "summary_id": ObjectId(summary_id),
                "user_email": user_email,
                "session_id": session_id,
                "rating": rating,
                "confused_concept": confused_concept.strip() if confused_concept else None,
                "comment": comment.strip() if comment else None,
                "created_at": datetime.utcnow()
            }
            
            result = self.feedback_collection.insert_one(feedback_doc)
            logger.info(f"Stored feedback for summary {summary_id} (rating: {rating})")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}", exc_info=True)
            raise
    
    def generate_reinforced_summary(
        self,
        topic: str,
        base_summary_text: str,
        feedback: Dict[str, Any]
    ) -> str:
        """
        Generate a reinforced summary based on feedback and lecture context.
        
        Args:
            topic: The topic being summarized
            base_summary_text: The original base summary
            feedback: Feedback dictionary with rating, confused_concept, etc.
            
        Returns:
            Generated reinforced summary text
        """
        logger.info(f"Generating reinforced summary for topic: {topic}")
        
        # Retrieve relevant lecture context using RAG
        rag_chain = _get_rag_chain()
        if rag_chain is None:
            raise ValueError("RAG system is not available")
        
        # Build query to get relevant context
        query = f"Provide detailed information about {topic} from lecture materials. Include examples, common mistakes, and clarification of concepts."
        result = rag_chain.invoke({"question": query})
        context_text = _extract_context_text(result)
        
        if not context_text:
            context_text = result.get("answer", "") if isinstance(result, dict) else str(result)
        
        # Build reinforcement prompt
        confused_concept = feedback.get("confused_concept", "")
        comment = feedback.get("comment", "")
        rating = feedback.get("rating", "not_helpful")
        
        prompt = self._build_reinforcement_prompt(
            topic=topic,
            base_summary=base_summary_text,
            context=context_text,
            confused_concept=confused_concept,
            comment=comment,
            rating=rating
        )
        
        # Generate reinforced summary using LLM
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3
        )
        
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            reinforced_summary = response.content if hasattr(response, "content") else str(response)
            logger.info("Reinforced summary generated successfully")
            return reinforced_summary
        except Exception as e:
            logger.error(f"Failed to generate reinforced summary: {e}", exc_info=True)
            raise
    
    def _build_reinforcement_prompt(
        self,
        topic: str,
        base_summary: str,
        context: str,
        confused_concept: str,
        comment: str,
        rating: str
    ) -> str:
        """Build the prompt for generating a reinforced summary."""
        
        confused_section = ""
        if confused_concept:
            confused_section = f"""
SPECIFIC FOCUS: The user found the concept "{confused_concept}" confusing. 
You MUST provide extra clarification, examples, and step-by-step explanations for this concept.
"""

        comment_section = ""
        if comment and str(comment).strip():
            comment_section = f"""
USER COMMENT:
{str(comment).strip()}

You MUST incorporate this comment into the improved summary.
"""
        
        rating_note = ""
        if rating == "not_helpful":
            rating_note = """
The user found the original summary not helpful. You need to:
- Simplify explanations
- Add more concrete examples
- Break down complex concepts into smaller steps
- Use analogies where appropriate
"""
        
        return f"""You are an expert educational assistant. Generate a REINFORCED SUMMARY for the topic: "{topic}"

The user has provided feedback on the original summary. Your task is to create an improved, more helpful summary.

{confused_section}
{comment_section}
{rating_note}

ORIGINAL SUMMARY:
{base_summary}

LECTURE CONTEXT (use this to ensure accuracy):
{context[:4000]}

REQUIRED STRUCTURE (follow this exactly):

## Overview
[Brief introduction to the topic]

## Key Concepts
[Break down the main concepts clearly. If a confused concept was mentioned, give it extra detail here]

## Worked Example
[Provide a concrete, step-by-step example that demonstrates the concepts]

## Common Mistakes
[Explain common mistakes students make with this topic]

## Self-Check
[Provide exactly 3 question-answer pairs that help students verify their understanding]

INSTRUCTIONS:
- Use ONLY information from the lecture context provided
- Write notes and explanations as normal prose text; put diagrams in markdown (fenced code block or ![alt](url))
- Format every URL as a markdown link [text](URL) so it is clickable
- If confused_concept was specified, dedicate extra space to clarifying it
- Make explanations clear and accessible
- Use markdown formatting
- Ensure the summary is comprehensive but not overwhelming
- The self-check section must have exactly 3 Q&A pairs
- Output ONLY the raw markdown. Do NOT wrap your entire response in a code block (no ``` at start/end). Your reply must be the summary itself so it renders as formatted text.

Generate the reinforced summary now:"""
    
    def _format_summary_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format MongoDB document for API response."""
        doc["_id"] = str(doc["_id"])
        if "base_summary_id" in doc and doc["base_summary_id"]:
            doc["base_summary_id"] = str(doc["base_summary_id"])
        if "feedback_id" in doc and doc["feedback_id"]:
            doc["feedback_id"] = str(doc["feedback_id"])
        if "audio_file_id" in doc and doc["audio_file_id"]:
            doc["audio_file_id"] = str(doc["audio_file_id"])
        return doc
    
    def get_feedback_for_summary(self, summary_id: str) -> List[Dict[str, Any]]:
        """Get all feedback for a specific summary."""
        try:
            feedback_docs = self.feedback_collection.find(
                {"summary_id": ObjectId(summary_id)}
            ).sort("created_at", -1)
            
            return [self._format_feedback_doc(doc) for doc in feedback_docs]
        except Exception as e:
            logger.error(f"Failed to get feedback: {e}", exc_info=True)
            return []

    def get_latest_feedback_for_topic(self, topic: str, user_email: Optional[str] = None, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get the latest feedback submitted for a topic (any summary), optionally scoped."""
        try:
            topic_lower = topic.lower().strip()
            query: Dict[str, Any] = {"topic": topic_lower}
            if user_email:
                query["$or"] = [{"user_email": user_email}, {"user_email": {"$exists": False}}]
            if session_id:
                query["session_id"] = session_id

            doc = self.feedback_collection.find_one(query, sort=[("created_at", -1)])
            return self._format_feedback_doc(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get latest feedback for topic: {e}", exc_info=True)
            return None

    def get_latest_feedback_for_summary(
        self,
        summary_id: str,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get the latest feedback for a given summary, optionally scoped by user/session."""
        try:
            query: Dict[str, Any] = {"summary_id": ObjectId(summary_id)}
            if user_email:
                query["$or"] = [{"user_email": user_email}, {"user_email": {"$exists": False}}]
            if session_id:
                query["session_id"] = session_id

            doc = self.feedback_collection.find_one(query, sort=[("created_at", -1)])
            return self._format_feedback_doc(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get latest feedback for summary: {e}", exc_info=True)
            return None
    
    def get_base_summary(self, summary_id: str) -> Optional[Dict[str, Any]]:
        """Get a base summary by ID."""
        try:
            doc = self.summaries_collection.find_one({"_id": ObjectId(summary_id)})
            return self._format_summary_doc(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get base summary: {e}", exc_info=True)
            return None
    
    def _format_feedback_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format feedback document for API response."""
        doc["_id"] = str(doc["_id"])
        doc["summary_id"] = str(doc["summary_id"])
        return doc
