"""Service for summary reinforcement and MongoDB operations."""

import logging
import re
from datetime import datetime
import wave
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
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
        feedback_type: Optional[str] = None,
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
            feedback_type: Optional "add_examples", "simplify", "more_detail", "clarify"
            
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
                "feedback_type": feedback_type,
                "created_at": datetime.utcnow()
            }
            
            result = self.feedback_collection.insert_one(feedback_doc)
            logger.info(f"Stored feedback for summary {summary_id} (rating: {rating})")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store feedback: {e}", exc_info=True)
            raise
    
    def _split_into_sections(self, text: str) -> List[str]:
        """Split summary into sections by ## or ### headers. Preserves all content including <figure> blocks."""
        if not (text or text.strip()):
            return [text] if text else []
        # Split before lines that start with ## or ### (at line start)
        parts = re.split(r"\n(?=##+\s)", text.strip())
        return [p.strip() for p in parts if p.strip()]

    def _normalize_header(self, line: str) -> str:
        """Normalize a section header for comparison (strip, single spaces)."""
        return " ".join(line.strip().split())

    def generate_reinforced_summary(
        self,
        topic: str,
        base_summary_text: str,
        feedback: Dict[str, Any]
    ) -> str:
        """
        Generate a reinforced summary based on feedback. Only the section that
        addresses the feedback is revised; all other content, images, and image
        explanations are preserved unchanged.
        """
        logger.info(f"Generating reinforced summary for topic: {topic} (only requested part will change)")
        
        # Retrieve relevant lecture context using RAG
        rag_chain = _get_rag_chain()
        if rag_chain is None:
            raise ValueError("RAG system is not available")
        
        query = f"Provide detailed information about {topic} from lecture materials. Include examples, common mistakes, and clarification of concepts."
        result = rag_chain.invoke({"question": query})
        context_text = _extract_context_text(result)
        if not context_text:
            context_text = result.get("answer", "") if isinstance(result, dict) else str(result)
        
        confused_concept = feedback.get("confused_concept", "") or ""
        comment = feedback.get("comment", "") or ""
        rating = feedback.get("rating", "not_helpful")
        feedback_type = feedback.get("feedback_type") or ""
        
        sections = self._split_into_sections(base_summary_text)
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3
        )
        
        try:
            # If we have multiple sections, revise only the one that matches the feedback
            if len(sections) >= 2:
                revised = self._generate_and_merge_revised_section(
                    llm=llm,
                    topic=topic,
                    base_summary_text=base_summary_text,
                    sections=sections,
                    context_text=context_text,
                    confused_concept=confused_concept,
                    comment=comment,
                    rating=rating,
                    feedback_type=feedback_type,
                )
                if revised is not None:
                    logger.info("Reinforced summary generated (only requested section changed)")
                    return revised
                logger.warning("Section-based revision did not succeed, falling back to full summary with preserve instructions")
            
            # Fallback: full summary with strict instructions to preserve unchanged parts and figures
            prompt = self._build_reinforcement_prompt(
                topic=topic,
                base_summary=base_summary_text,
                context=context_text,
                confused_concept=confused_concept,
                comment=comment,
                rating=rating,
                feedback_type=feedback_type,
            )
            response = llm.invoke([HumanMessage(content=prompt)])
            reinforced_summary = response.content if hasattr(response, "content") else str(response)
            logger.info("Reinforced summary generated (full summary with preserve instructions)")
            return reinforced_summary
        except Exception as e:
            logger.error(f"Failed to generate reinforced summary: {e}", exc_info=True)
            raise

    def _generate_and_merge_revised_section(
        self,
        llm,
        topic: str,
        base_summary_text: str,
        sections: List[str],
        context_text: str,
        confused_concept: str,
        comment: str,
        rating: str,
        feedback_type: str = "",
    ) -> Optional[str]:
        """Ask LLM to revise only one section; merge it back and return full summary or None on failure."""
        prompt = self._build_revise_section_prompt(
            topic=topic,
            base_summary=base_summary_text,
            context=context_text[:4000],
            confused_concept=confused_concept,
            comment=comment,
            rating=rating,
            feedback_type=feedback_type,
        )
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = response.content if hasattr(response, "content") else str(response)
        raw = (raw or "").strip()
        
        # Parse SECTION_HEADER: ... and REVISED_SECTION: ...
        header_match = re.search(r"SECTION_HEADER:\s*\n?\s*(##+\s+.+?)(?=\n|REVISED_SECTION:|$)", raw, re.DOTALL | re.IGNORECASE)
        section_match = re.search(r"REVISED_SECTION:\s*\n?(.+)", raw, re.DOTALL | re.IGNORECASE)
        if not header_match or not section_match:
            return None
        section_header = self._normalize_header(header_match.group(1).strip())
        revised_section = section_match.group(1).strip()
        
        # Ensure revised section starts with the same header for consistency
        if not revised_section.startswith("##"):
            revised_section = section_header + "\n\n" + revised_section
        elif self._normalize_header(revised_section.split("\n")[0]) != section_header:
            first_line = revised_section.split("\n")[0]
            section_header = self._normalize_header(first_line)
        
        # Find which section to replace (match by header)
        for i, sec in enumerate(sections):
            first_line = sec.split("\n")[0] if sec else ""
            if self._normalize_header(first_line) == section_header:
                new_sections = sections[:i] + [revised_section] + sections[i + 1:]
                return "\n\n".join(new_sections)
            if first_line.strip().startswith("##") and section_header in self._normalize_header(first_line):
                new_sections = sections[:i] + [revised_section] + sections[i + 1:]
                return "\n\n".join(new_sections)
        return None

    def _feedback_type_instruction(self, feedback_type: str) -> str:
        """Return instruction line for feedback_type (more_detail, simplify, clarify, add_examples)."""
        if not feedback_type:
            return ""
        ft = (feedback_type or "").strip().lower().replace("-", "_")
        if ft == "more_detail":
            return "\nUSER REQUEST: More detail. Make the relevant section and any image explanations (figcaption) in it more detailed and informative.\n"
        if ft == "simplify":
            return "\nUSER REQUEST: Simplify. Use simpler language in the relevant section and simplify any image explanations (figcaption) in that section.\n"
        if ft == "clarify":
            return "\nUSER REQUEST: Clarify concepts. Make the explanation clearer in the relevant section and clarify any image explanations (figcaption) in that section.\n"
        if ft == "add_examples":
            return "\nUSER REQUEST: Add examples. Add concrete examples in the relevant section; if the section has figure captions, make them more example-oriented where appropriate.\n"
        return f"\nUSER REQUEST: {feedback_type.replace('_', ' ').title()}. Address this in the relevant section and in any image explanations in that section.\n"

    def _build_revise_section_prompt(
        self,
        topic: str,
        base_summary: str,
        context: str,
        confused_concept: str,
        comment: str,
        rating: str,
        feedback_type: str = "",
    ) -> str:
        """Build prompt that asks for only the revised section (and its header), including image explanations."""
        confused_section = ""
        if confused_concept:
            confused_section = f'\nThe user found the concept "{confused_concept}" confusing. Focus on clarifying that concept in the relevant section.\n'
        comment_section = ""
        if comment and str(comment).strip():
            comment_section = f"\nUSER COMMENT to incorporate: {str(comment).strip()}\n"
        rating_note = ""
        if rating == "not_helpful":
            rating_note = "\nThe user found the summary not helpful; simplify and add examples in the relevant section.\n"
        feedback_type_line = self._feedback_type_instruction(feedback_type)
        return f"""You are an expert educational assistant. The user gave feedback on a summary. Your task is to revise ONLY THE ONE SECTION that should change based on the feedback. Do NOT change any other section.
{confused_section}{comment_section}{rating_note}{feedback_type_line}

IMPORTANT - Images and image explanations: If the section you are revising contains <figure>...</figure> blocks (image with <figcaption> explanation), you MUST include them in your revised section and UPDATE the figcaption text to match the feedback (e.g. more detailed, simpler, or clearer). Keep the same <figure> structure and the same img src= URL; only change the explanation text inside <figcaption> so it addresses the user's request. If there are no figures in that section, just revise the text.

ORIGINAL FULL SUMMARY (with sections; do not change sections you are not revising):
{base_summary}

LECTURE CONTEXT (use for accuracy):
{context[:3500]}

INSTRUCTIONS:
1. Identify the single section (e.g. ## Key Concepts, ## Overview) that should be revised to address the feedback.
2. Output your response in this EXACT format (copy the labels exactly):

SECTION_HEADER:
## Section Name

REVISED_SECTION:
[Paste here ONLY the revised section content, starting with the same ## header. Include any <figure>...</figure> blocks that belong to this section; if you update their <figcaption> text to match the feedback, do so. Use markdown and HTML as in the original. No other sections.]

Output nothing else after the revised section."""
    
    def _build_reinforcement_prompt(
        self,
        topic: str,
        base_summary: str,
        context: str,
        confused_concept: str,
        comment: str,
        rating: str,
        feedback_type: str = "",
    ) -> str:
        """Build the prompt for full-summary fallback: change only the part that addresses feedback; allow updating image explanations in that part."""
        
        confused_section = ""
        if confused_concept:
            confused_section = f"""
SPECIFIC FOCUS: The user found the concept "{confused_concept}" confusing. Revise ONLY the section that covers this concept.
"""

        comment_section = ""
        if comment and str(comment).strip():
            comment_section = f"""
USER COMMENT: {str(comment).strip()}
Incorporate this only in the relevant section.
"""
        
        rating_note = ""
        if rating == "not_helpful":
            rating_note = """
The user found the summary not helpful. Simplify and add examples only in the section that needs improvement.
"""
        feedback_type_line = self._feedback_type_instruction(feedback_type)
        
        return f"""You are an expert educational assistant. The user gave feedback on a summary. Your task is to output the FULL summary with ONLY the minimal change: revise only the part that addresses the feedback. All other content must stay EXACTLY the same.
{feedback_type_line}

CRITICAL:
- Preserve EXACTLY every section that does NOT relate to the feedback (same text, same <figure> blocks).
- In the ONE section that you revise to address the feedback: you MAY update both the prose and any <figure>...</figure> blocks in that section. For figures in the revised section: keep the same <figure> structure and img src= URL; you MAY change the <figcaption> explanation text to match the feedback (more detailed, simpler, or clearer).
- Do not change any other section or any figure outside the revised section.

{confused_section}
{comment_section}
{rating_note}

ORIGINAL SUMMARY (preserve all of this except the one part you revise and its image explanations):
{base_summary}

LECTURE CONTEXT (use for accuracy when revising):
{context[:4000]}

INSTRUCTIONS:
- Output the COMPLETE summary: same structure, same sections.
- Change ONLY the section that addresses the confused concept or user comment; within that section you may also update image explanations (figcaption) to match the feedback.
- Copy every other section and every <figure> block outside that section exactly from the original.
- Use markdown formatting. Output ONLY the raw markdown (no ``` wrapper).

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
