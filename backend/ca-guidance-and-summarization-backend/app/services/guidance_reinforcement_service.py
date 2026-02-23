"""Service for CA guidance reinforcement and MongoDB operations."""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from bson.objectid import ObjectId

from app.core.database import get_database
from app.ca_guidance.tools.rag_tool import _get_rag_chain, _extract_context_text
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.core.config import settings

logger = logging.getLogger(__name__)


class GuidanceReinforcementService:
    """Service for managing CA guidance documents and reinforcement from feedback."""

    def __init__(self):
        self.db = get_database()
        self.guidances_collection = self.db.guidances
        self.feedback_collection = self.db.guidance_feedback
        self._create_indexes()

    def _create_indexes(self):
        try:
            self.guidances_collection.create_index([("user_email", 1), ("guidance_type", 1)])
            self.feedback_collection.create_index([("guidance_id", 1)])
            self.feedback_collection.create_index([("user_email", 1), ("guidance_id", 1), ("created_at", -1)])
            logger.info("Guidance database indexes created successfully")
        except Exception as e:
            logger.warning(f"Failed to create guidance indexes (may already exist): {e}")

    def store_base_guidance(
        self,
        report_text: str,
        images: Optional[List[str]] = None,
        user_email: Optional[str] = None,
    ) -> str:
        """
        Store a base guidance report (from run_guidance). Returns the new guidance document ID.
        """
        try:
            doc = {
                "report_text": report_text,
                "guidance_type": "base",
                "user_email": user_email,
                "images": images or [],
                "created_at": datetime.utcnow(),
            }
            result = self.guidances_collection.insert_one(doc)
            guidance_id = str(result.inserted_id)
            logger.info(f"Stored base guidance (id: {guidance_id})")
            return guidance_id
        except Exception as e:
            logger.error(f"Failed to store base guidance: {e}", exc_info=True)
            raise

    def get_guidance(self, guidance_id: str, user_email: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a guidance document by ID."""
        try:
            doc = self.guidances_collection.find_one({"_id": ObjectId(guidance_id)})
            if not doc:
                return None
            if user_email and doc.get("user_email") and doc["user_email"] != user_email:
                return None
            return self._format_guidance_doc(doc)
        except Exception as e:
            logger.error(f"Failed to get guidance: {e}", exc_info=True)
            return None

    def store_feedback(
        self,
        guidance_id: str,
        rating: str,
        confused_concept: Optional[str] = None,
        comment: Optional[str] = None,
        feedback_type: Optional[str] = None,
        deadline_text: Optional[str] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Store user feedback for a guidance report."""
        if rating not in ("helpful", "not_helpful"):
            raise ValueError("Rating must be 'helpful' or 'not_helpful'")
        try:
            feedback_doc = {
                "guidance_id": ObjectId(guidance_id),
                "user_email": user_email,
                "session_id": session_id,
                "rating": rating,
                "confused_concept": confused_concept.strip() if confused_concept else None,
                "comment": comment.strip() if comment else None,
                "feedback_type": feedback_type,
                "deadline_text": deadline_text.strip() if deadline_text else None,
                "created_at": datetime.utcnow(),
            }
            result = self.feedback_collection.insert_one(feedback_doc)
            logger.info(f"Stored guidance feedback for {guidance_id} (rating: {rating})")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Failed to store guidance feedback: {e}", exc_info=True)
            raise

    def get_latest_feedback_for_guidance(
        self,
        guidance_id: str,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get the latest feedback for a guidance document."""
        try:
            query: Dict[str, Any] = {"guidance_id": ObjectId(guidance_id)}
            if user_email:
                query["$or"] = [{"user_email": user_email}, {"user_email": {"$exists": False}}]
            if session_id:
                query["session_id"] = session_id
            doc = self.feedback_collection.find_one(query, sort=[("created_at", -1)])
            return self._format_feedback_doc(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get latest feedback: {e}", exc_info=True)
            return None

    def store_reinforced_guidance(
        self,
        base_guidance_id: str,
        report_text: str,
        feedback_id: Optional[str] = None,
        images: Optional[List[str]] = None,
        user_email: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Store or replace reinforced guidance for a base guidance. One reinforced per base per user."""
        try:
            doc = {
                "report_text": report_text,
                "guidance_type": "reinforced",
                "base_guidance_id": ObjectId(base_guidance_id),
                "feedback_id": ObjectId(feedback_id) if feedback_id else None,
                "user_email": user_email,
                "session_id": session_id,
                "images": images or [],
                "created_at": datetime.utcnow(),
            }
            filt: Dict[str, Any] = {"base_guidance_id": ObjectId(base_guidance_id), "guidance_type": "reinforced"}
            if user_email:
                filt["user_email"] = user_email
            result = self.guidances_collection.update_one(filt, {"$set": doc}, upsert=True)
            if result.upserted_id:
                out_id = str(result.upserted_id)
            else:
                updated = self.guidances_collection.find_one(filt)
                out_id = str(updated["_id"])
            logger.info(f"Stored reinforced guidance for base {base_guidance_id} (id: {out_id})")
            return out_id
        except Exception as e:
            logger.error(f"Failed to store reinforced guidance: {e}", exc_info=True)
            raise

    def get_reinforced_guidance(
        self,
        base_guidance_id: str,
        user_email: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get reinforced guidance for a base guidance ID if it exists."""
        try:
            query: Dict[str, Any] = {
                "base_guidance_id": ObjectId(base_guidance_id),
                "guidance_type": "reinforced",
            }
            if user_email:
                query["$or"] = [{"user_email": user_email}, {"user_email": {"$exists": False}}]
            doc = self.guidances_collection.find_one(query)
            return self._format_guidance_doc(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get reinforced guidance: {e}", exc_info=True)
            return None

    def get_latest_guidance_for_reinforcement(
        self,
        base_guidance_id: str,
        user_email: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get the most recent version of the guidance. The system must always work with this
        version so that all feedback (deadline updates, add more links, simplify language,
        clarifications) is applied in sequence to the same document.

        Returns the reinforced document if it exists (incorporates all prior changes);
        otherwise returns the base guidance. Callers must use this for any reinforcement
        so the latest changes are never lost.
        """
        reinforced = self.get_reinforced_guidance(base_guidance_id, user_email=user_email)
        if reinforced:
            logger.info(f"Using latest reinforced guidance as source (base={base_guidance_id})")
            return reinforced
        base = self.get_guidance(base_guidance_id, user_email=user_email)
        if base and base.get("guidance_type") == "base":
            logger.info(f"Using base guidance as source (base={base_guidance_id})")
            return base
        return None

    def generate_reinforced_guidance(
        self,
        base_report_text: str,
        feedback: Dict[str, Any],
        assignment_context: Optional[str] = None,
    ) -> str:
        """
        Generate reinforced guidance by applying feedback to the current report text.
        base_report_text must be the latest version (from get_latest_guidance_for_reinforcement)
        so that deadline updates, links, and other changes are preserved. Uses RAG and LLM.
        """
        logger.info("Generating reinforced guidance from feedback (applying to latest version)")

        context_text = ""
        rag_chain = _get_rag_chain()
        if rag_chain:
            query = "DBMS assignment guidance: ER models, normalization, SQL, constraints, design. Provide detailed context for assignment solutions."
            result = rag_chain.invoke({"question": query})
            context_text = _extract_context_text(result) or (result.get("answer", "") if isinstance(result, dict) else str(result))
        if assignment_context:
            context_text = (context_text + "\n\n" + assignment_context)[:6000]

        confused_concept = feedback.get("confused_concept") or ""
        comment = feedback.get("comment") or ""
        rating = feedback.get("rating", "not_helpful")
        feedback_type = feedback.get("feedback_type") or ""
        deadline_text = feedback.get("deadline_text") or ""

        prompt = self._build_reinforcement_prompt(
            base_report=base_report_text,
            context=context_text,
            confused_concept=confused_concept,
            comment=comment,
            rating=rating,
            feedback_type=feedback_type,
            deadline_text=deadline_text,
        )

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3,
        )
        try:
            response = llm.invoke([HumanMessage(content=prompt)])
            out = response.content if hasattr(response, "content") else str(response)
            logger.info("Reinforced guidance generated successfully")
            return out
        except Exception as e:
            logger.error(f"Failed to generate reinforced guidance: {e}", exc_info=True)
            raise

    def _build_reinforcement_prompt(
        self,
        base_report: str,
        context: str,
        confused_concept: str,
        comment: str,
        rating: str,
        feedback_type: str,
        deadline_text: str = "",
    ) -> str:
        """Build the prompt for generating reinforced CA guidance with CA-specific feedback types."""
        confused_section = ""
        if confused_concept:
            confused_section = f"""
SPECIFIC FOCUS: The user found this part confusing or has a doubt: "{confused_concept}".
You MUST add extra clarification, step-by-step explanation, or examples for that part.
"""

        comment_section = ""
        if comment and comment.strip():
            comment_section = f"""
USER COMMENT:
{comment.strip()}

Incorporate this feedback into the improved guidance.
"""

        type_section = ""
        if feedback_type == "add_more_links":
            type_section = """
USER REQUESTED: Add more links.
You MUST add or expand a "### Related Web Resources" section with more useful links: articles, tutorials, YouTube videos, or official docs related to DBMS, ER modeling, SQL, normalization, etc. Use markdown link format [Title](URL). If the original had this section, add more links to it; otherwise create the section.
"""
        elif feedback_type == "new_deadline_event":
            type_section = """
USER REQUESTED: Set new deadline / Create event.
You MUST add or update a "### Deadline / Calendar Confirmation" section (or "### Your new deadline") in the guidance. In that section, write the new deadline clearly in normal text so the user sees it stated in the document.
Do NOT use any deadline previously extracted from the document. Use ONLY the user-provided new deadline given below.
"""
            if deadline_text and deadline_text.strip():
                dl = deadline_text.strip()
                type_section += f"""
USER PROVIDED NEW DEADLINE (use this and only this in the guidance; ignore any document deadline): **{dl}**

In the "### Deadline / Calendar Confirmation" section, write something like:
- "Your new deadline is **{dl}**. This has been added to your calendar."
Do NOT mention credentials, API setup, or "confirm this deadline event successfully". Just state the deadline clearly and that it was added to the calendar.
"""
        elif feedback_type == "doubt_on_questions":
            type_section = """
USER REQUESTED: Ask doubt on questions.
The user has doubts about specific assignment questions or parts. Add a dedicated FAQ or "Common doubts clarified" subsection that addresses likely doubts: clearer step-by-step answers, alternative explanations, or worked examples for the trickier parts. Use the confused_concept or comment above to focus on what to clarify.
"""
        elif feedback_type == "simplify_language":
            type_section = """
USER REQUESTED: Simplify language.
Rewrite explanations in simpler, more accessible language. Avoid jargon where possible; when technical terms are needed, define them briefly. Use short sentences and bullet points. Keep the same content and structure but make it easier to follow.
"""
        elif feedback_type:
            type_section = f"""
USER REQUESTED: {feedback_type.replace("_", " ").title()}
Address this in the improved guidance.
"""

        rating_note = ""
        if rating == "not_helpful":
            rating_note = """
The user found the original guidance not helpful. You should:
- Simplify explanations and break down steps more clearly
- Add more concrete examples or SQL/ER snippets where relevant
- Align strictly with DBMS lecture content (ER, EER, normalization, SQL, constraints)
"""

        return f"""You are an expert DBMS tutor. Generate a REINFORCED ASSIGNMENT GUIDANCE document by applying the user's feedback to the CURRENT guidance below.

The text below is the LATEST VERSION of the guidance (it may already include a deadline, added links, or prior improvements). Apply the requested changes on top of this version so all updates are preserved and the user sees one up-to-date document.

{confused_section}
{comment_section}
{type_section}
{rating_note}

CURRENT GUIDANCE (markdown) — improve this document with the feedback above:
{base_report}

LECTURE/CONTEXT (use for accuracy):
{context[:4000] if context else "Use your DBMS knowledge."}

INSTRUCTIONS:
- Output a complete, improved guidance document in the same markdown style
- Write all notes and explanatory text as **normal prose** (paragraphs, bullet lists). Do not put notes inside code blocks; use code blocks only for SQL, code, or diagram syntax
- Put diagrams in markdown: use a fenced code block for diagram text/ASCII (e.g. ER diagram syntax) or ![alt](url) for images
- Format every URL as a markdown link so it is clickable: [link text](URL). Never output bare URLs as plain text
- Keep the same overall structure (sections, headings) unless feedback asks to change it
- Add or expand clarification where the user was confused or had doubts
- Preserve any SQL, ER descriptions, or diagrams from the original (in code blocks or image markdown)
- Do not remove content unless it was wrong; improve and extend
- For "add_more_links": ensure a strong Related Web Resources section with multiple links in [text](url) format
- For "simplify_language": use plain, clear language throughout

CRITICAL: Output ONLY the raw markdown content. Do NOT wrap your entire response in a code block. Do not start with ```markdown or ``` and do not end with ```. Your reply must be the guidance document itself so it can be rendered as formatted text, not as a single code block.

Generate the reinforced guidance now:"""

    def _format_guidance_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        doc["_id"] = str(doc["_id"])
        if doc.get("base_guidance_id"):
            doc["base_guidance_id"] = str(doc["base_guidance_id"])
        if doc.get("feedback_id"):
            doc["feedback_id"] = str(doc["feedback_id"])
        return doc

    def _format_feedback_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        doc["_id"] = str(doc["_id"])
        doc["guidance_id"] = str(doc["guidance_id"])
        return doc
