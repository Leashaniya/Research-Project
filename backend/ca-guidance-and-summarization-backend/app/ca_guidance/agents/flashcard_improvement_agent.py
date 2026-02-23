# app/ca_guidance/agents/flashcard_improvement_agent.py

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.ca_guidance.tools.rag_tool import _get_rag_chain, _extract_context_text

logger = logging.getLogger(__name__)


class FlashcardImprovementError(Exception):
    """Raised when flashcard improvement fails."""
    pass


def _build_improvement_prompt(
    question: str,
    answer: str,
    bloom_level: str,
    feedback_type: Optional[str],
    comment: Optional[str],
    context_text: str,
    topic: str
) -> str:
    """Build the prompt for improving a flashcard based on feedback."""
    
    feedback_instruction = ""
    if feedback_type == "add_examples":
        feedback_instruction = "ADD more concrete examples to help understanding."
    elif feedback_type == "simplify":
        feedback_instruction = "SIMPLIFY the language to make it easier to understand. Use simpler words and shorter sentences."
    elif feedback_type == "more_detail":
        feedback_instruction = "ADD more detail and depth to the explanation."
    elif feedback_type == "clarify":
        feedback_instruction = "CLARIFY the content to remove any ambiguity."
    elif comment:
        feedback_instruction = f"Apply this specific feedback: {comment}"
    else:
        feedback_instruction = "Improve the flashcard to be clearer and more educational."
    
    return f"""
You are an educational content improvement assistant.

You must improve the following flashcard based on user feedback.

ORIGINAL FLASHCARD:
- Bloom's Taxonomy Level: {bloom_level}
- Question: {question}
- Answer: {answer}

USER FEEDBACK:
{feedback_instruction}
{f"Additional comment: {comment}" if comment and feedback_type != "other" else ""}

TOPIC CONTEXT (use this to ensure accuracy):
\"\"\"{context_text[:4000]}\"\"\"

RULES:
1. Keep the same Bloom's taxonomy level ({bloom_level})
2. Maintain educational value
3. Use ONLY information from the provided context
4. Keep answers concise (1-4 sentences)
5. Apply the feedback directly to improve the content

Output MUST be valid JSON ONLY (no markdown, no extra text):
{{
  "question": "improved question text",
  "answer": "improved answer text",
  "improvement_notes": "brief explanation of changes made"
}}
""".strip()


def _safe_json_loads(text: str) -> Dict[str, Any]:
    """Parse JSON; if extra text exists, extract the outermost JSON object."""
    text = (text or "").strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])

    raise FlashcardImprovementError("Model did not return valid JSON.")


def _validate_improvement_output(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the improved flashcard output."""
    if not isinstance(data, dict):
        raise FlashcardImprovementError("Output must be a JSON object.")

    required_fields = ["question", "answer", "improvement_notes"]
    for field in required_fields:
        if field not in data:
            raise FlashcardImprovementError(f'Output must contain "{field}".')
        if not isinstance(data[field], str) or not data[field].strip():
            raise FlashcardImprovementError(f'"{field}" must be a non-empty string.')

    return data


@dataclass
class FlashcardImprovementAgent:
    """
    Agent for improving flashcards based on user feedback.
    Uses RAG to retrieve context and LLM to generate improvements.
    """
    llm: Any
    max_retries: int = 2

    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt."""
        if hasattr(self.llm, "invoke"):
            try:
                from langchain_core.messages import HumanMessage
                result = self.llm.invoke([HumanMessage(content=prompt)])
            except (ImportError, TypeError, AttributeError):
                result = self.llm.invoke(prompt)
            
            if hasattr(result, "content"):
                return result.content
            if hasattr(result, "text"):
                return result.text
            return str(result)
        
        if hasattr(self.llm, "generate"):
            result = self.llm.generate(prompt)
            if hasattr(result, "generations") and result.generations:
                return result.generations[0][0].text
            return str(result)
        
        if callable(self.llm):
            result = self.llm(prompt)
            if hasattr(result, "content"):
                return result.content
            if hasattr(result, "text"):
                return result.text
            return str(result)
        
        raise FlashcardImprovementError("LLM must have generate()/invoke() or be callable.")

    def _retrieve_context(self, topic: str) -> str:
        """Retrieve relevant context for the topic from RAG."""
        rag_chain = _get_rag_chain()
        if rag_chain is None:
            logger.warning("RAG system not available, using empty context")
            return ""

        query = f"Find lecture slide content about: {topic}. Return relevant details, definitions, examples."
        result = rag_chain.invoke({"question": query})
        context_text = _extract_context_text(result)

        if not context_text:
            if isinstance(result, dict):
                context_text = str(result.get("answer", "")).strip()
            else:
                context_text = str(result).strip()

        return context_text.strip()

    def improve_flashcard(
        self,
        topic: str,
        question: str,
        answer: str,
        bloom_level: str,
        feedback_type: Optional[str] = None,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Improve a flashcard based on user feedback.
        
        Args:
            topic: The topic of the flashcard set
            question: Original question text
            answer: Original answer text
            bloom_level: Bloom's taxonomy level
            feedback_type: Type of feedback (add_examples, simplify, more_detail, etc.)
            comment: Additional user comment
            
        Returns:
            Dict with improved question, answer, and improvement_notes
        """
        # Get context for accurate improvements
        context_text = self._retrieve_context(topic)
        
        prompt = _build_improvement_prompt(
            question=question,
            answer=answer,
            bloom_level=bloom_level,
            feedback_type=feedback_type,
            comment=comment,
            context_text=context_text,
            topic=topic
        )

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self._call_llm(prompt)
                data = _safe_json_loads(raw)
                result = _validate_improvement_output(data)
                
                logger.info(f"Successfully improved flashcard for topic '{topic}', level '{bloom_level}'")
                return result
                
            except Exception as e:
                last_err = e
                logger.warning(f"Improvement attempt {attempt + 1} failed: {e}")
                prompt = prompt + "\n\nREMINDER: Return ONLY valid JSON. No markdown. No extra text."

        raise FlashcardImprovementError(f"Flashcard improvement failed. Last error: {last_err}")
