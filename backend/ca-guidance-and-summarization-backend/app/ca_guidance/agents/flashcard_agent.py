# app/ca_guidance/agents/flashcard_agent.py

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.ca_guidance.tools.rag_tool import _get_rag_chain, _extract_context_text

logger = logging.getLogger(__name__)

BLOOM_LEVELS = ["remember", "understand", "apply", "analyze", "evaluate", "create"]


class FlashcardAgentError(Exception):
    """Raised when flashcard generation fails or output is invalid."""
    pass


def _build_flashcard_query(topic: str) -> str:
    # This query is meant to retrieve relevant chunks (docs) from your RAG chain.
    # Keep it "retrieval-friendly" (topic-focused) rather than asking for full answer.
    return (
        f"Find lecture slide content about: {topic}. "
        f"Return the most relevant details, definitions, steps, examples, and comparisons."
    )


def _build_bloom_prompt(topic: str, context_text: str) -> str:
    return f"""
You are an educational assistant.

Using ONLY the provided lecture slide content, generate flashcards for the topic: "{topic}".

STRICT RULES:
- Follow Bloom’s Taxonomy using EXACTLY these 6 keys:
  remember, understand, apply, analyze, evaluate, create
- For EACH level, generate EXACTLY 5 flashcards.
- Each flashcard must be an object with:
  - "question": string
  - "answer": string
- Answers must be concise (1–4 sentences).
- Do NOT add outside knowledge. If the content is missing, rephrase to stay within the content.
- Output MUST be valid JSON ONLY (no markdown, no extra text).

Required JSON format:
{{
  "topic": "{topic}",
  "flashcards": {{
    "remember": [{{"question":"...","answer":"..."}}, ...],
    "understand": [{{"question":"...","answer":"..."}}, ...],
    "apply": [{{"question":"...","answer":"..."}}, ...],
    "analyze": [{{"question":"...","answer":"..."}}, ...],
    "evaluate": [{{"question":"...","answer":"..."}}, ...],
    "create": [{{"question":"...","answer":"..."}}, ...]
  }}
}}

Lecture Slide Content:
\"\"\"{context_text}\"\"\"
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

    raise FlashcardAgentError("Model did not return valid JSON.")


def _validate_output(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise FlashcardAgentError("Output must be a JSON object.")

    if "topic" not in data or "flashcards" not in data:
        raise FlashcardAgentError('Output must contain "topic" and "flashcards".')

    flashcards = data["flashcards"]
    if not isinstance(flashcards, dict):
        raise FlashcardAgentError('"flashcards" must be a JSON object.')

    for lvl in BLOOM_LEVELS:
        if lvl not in flashcards:
            raise FlashcardAgentError(f'Missing Bloom level "{lvl}".')

        cards = flashcards[lvl]
        if not isinstance(cards, list) or len(cards) != 5:
            raise FlashcardAgentError(f'Bloom level "{lvl}" must contain exactly 5 flashcards.')

        for i, c in enumerate(cards):
            if not isinstance(c, dict):
                raise FlashcardAgentError(f'Flashcard {lvl}[{i}] must be an object.')
            if "question" not in c or "answer" not in c:
                raise FlashcardAgentError(f'Flashcard {lvl}[{i}] must have "question" and "answer".')
            if not isinstance(c["question"], str) or not isinstance(c["answer"], str):
                raise FlashcardAgentError(f'Flashcard {lvl}[{i}] question/answer must be strings.')
            if not c["question"].strip() or not c["answer"].strip():
                raise FlashcardAgentError(f'Flashcard {lvl}[{i}] question/answer cannot be empty.')

    return data


@dataclass
class FlashcardAgent:
    """
    Integrates with your existing RAG chain cache via _get_rag_chain().

    You inject:
      - llm: must provide generate(prompt: str) -> str
        (or invoke(prompt: str) -> str, or be callable)
    """
    llm: Any
    top_k: int = 8
    min_context_chars: int = 200
    max_retries: int = 1

    def _call_llm(self, prompt: str) -> str:
        # Handle ChatOpenAI and other LangChain chat models
        if hasattr(self.llm, "invoke"):
            # ChatOpenAI expects a list of messages or a string
            # For simplicity, we'll pass a string and let it handle it
            # If it's a chat model, we might need to format it properly
            try:
                from langchain_core.messages import HumanMessage
                # Try using HumanMessage for chat models
                result = self.llm.invoke([HumanMessage(content=prompt)])
            except (ImportError, TypeError, AttributeError):
                # Fallback: try passing string directly
                result = self.llm.invoke(prompt)
            
            # Extract content from result
            if hasattr(result, "content"):
                return result.content
            if hasattr(result, "text"):
                return result.text
            return str(result)
        
        if hasattr(self.llm, "generate"):
            result = self.llm.generate(prompt)
            # Handle different return types
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
        
        raise FlashcardAgentError("LLM must have generate()/invoke() or be callable.")

    def _retrieve_context(self, topic: str) -> str:
        rag_chain = _get_rag_chain()
        if rag_chain is None:
            raise FlashcardAgentError(
                "RAG system is not available. Build the vectorstore first by ingesting lecture PDFs."
            )

        query = _build_flashcard_query(topic)
        result = rag_chain.invoke({"question": query})

        # Prefer docs context (raw slide chunks) rather than the synthesized answer
        context_text = _extract_context_text(result)

        # Fallback: if docs not available, use 'answer' (less ideal but better than nothing)
        if not context_text:
            if isinstance(result, dict):
                context_text = str(result.get("answer", "")).strip()
            else:
                context_text = str(result).strip()

        # Optional: truncate huge context to keep prompts stable
        # (tune this as needed)
        if len(context_text) > 12000:
            context_text = context_text[:12000]

        return context_text.strip()

    def generate_flashcards(self, topic: str) -> Dict[str, Any]:
        topic = (topic or "").strip()
        if not topic:
            raise FlashcardAgentError("Topic cannot be empty.")

        context_text = self._retrieve_context(topic)
        if len(context_text) < self.min_context_chars:
            raise FlashcardAgentError(
                "Not enough slide content found for this topic. Try a more specific topic."
            )

        prompt = _build_bloom_prompt(topic, context_text)

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = self._call_llm(prompt)
                data = _safe_json_loads(raw)
                return _validate_output(data)
            except Exception as e:
                last_err = e
                # tighten prompt on retry
                prompt = prompt + "\n\nREMINDER: Return ONLY valid JSON. No markdown. No extra text."

        raise FlashcardAgentError(f"Flashcard generation failed. Last error: {last_err}")
