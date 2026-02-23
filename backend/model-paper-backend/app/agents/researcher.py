import faiss
import numpy as np
import json
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
from .base import BaseAgent
from app.core.paths import SLIDES_EXTRACTION_DIR, SLIDES_EMB_DIR
from app.core.llm_factory import get_llm_client
from app.core.config import settings

class ContentResearcher(BaseAgent):
    """
    The Content Researcher Agent (Librarian).
    Role: Retrieve the best context from Lecture Slides for a given query.
    """

    def __init__(self, config=None):
        super().__init__(name="Content Researcher", config=config)
        self.chunks_path = SLIDES_EXTRACTION_DIR / "slides_chunks.jsonl"
        self.index_path = SLIDES_EMB_DIR / "slides_faiss_index_flatip.index"
        
        self.model = None
        self.index = None
        self.chunks = []
        
        # Lazy load to avoid startup overhead if not used
        self._loaded = False
        
        # LLM for summarization
        self.llm_client = None
        try:
             self.llm_client = get_llm_client()
        except Exception as e:
             print(f"Researcher LLM Init Failed: {e}")

    def _load_resources(self):
        if self._loaded:
            return

        self.log("Loading research resources (FAISS + MiniLM)...")
        try:
            # Load Embedder
            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            
            # Load FAISS Index
            self.index = faiss.read_index(str(self.index_path))
            
            # Load Chunks
            with open(self.chunks_path, "r", encoding="utf-8") as f:
                self.chunks = [json.loads(line) for line in f if line.strip()]
                
            self._loaded = True
            self.log("Resources loaded successfully.")
        except Exception as e:
            self.log(f"Error loading resources: {e}")
            raise e

    async def run(self, input_data: Dict[str, Any]) -> str:
        """
        Input: {"query": "Explain Normalization"}
        Output: Combined string of relevant slide context.
        """
        query = input_data.get("query")
        if not query:
            return ""

        self._load_resources()
        
        # Search
        self.log(f"Searching for: '{query}'")
        q_emb = self.model.encode([query])
        q_emb = np.asarray(q_emb, dtype="float32")
        faiss.normalize_L2(q_emb)
        
        top_k = self.config.get("top_k", 5)
        D, I = self.index.search(q_emb, top_k)
        
        hits = []
        for idx in I[0]:
            if idx < 0 or idx >= len(self.chunks):
                continue
            hits.append(self.chunks[int(idx)])
            
        # raw_text = self._format_hits(hits)
        # Summarize using LLM
        return await self._summarize_hits(hits, query)

    async def _summarize_hits(self, hits: List[dict], query: str) -> str:
        """Use LLM to extract snippets/facts."""
        raw_text = self._format_hits(hits)
        if not self.llm_client:
             return raw_text
        
        prompt = f"""
        You are a Research Assistant for a Database exam setter.
        Extract exact evidence from the provided lecture slides content to help answer a question about: "{query}".
        
        Output Format:
        - **Key Facts**: 3-6 bullet points with specific technical details (definitions, steps, rules).
        - **Key Terms**: A list of important database terms found in the text.
        - **Diagrams**: If any diagrams/figures are mentioned, describe them briefly with a caption (e.g. "Figure 3.1: ER Notation").
        
        Usage Rules:
        - Do NOT help answer the question directly. Just provide the raw facts/evidence.
        - Be concise.
        - If no relevant info found, say "No relevant evidence found."
        
        Source Content:
        {raw_text[:8000]}
        """
        
        try:
            response = self.llm_client.chat.completions.create(
                model=settings.OPENAI_MODEL or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0].message.content
        except Exception as e:
            self.log(f"Summarization failed: {e}")
            return raw_text

    def _format_hits(self, hits: List[dict]) -> str:
        parts = []
        for i, c in enumerate(hits, 1):
            header = f"[SOURCE: {c.get('pdf_stem')} | Slide {c.get('slide_no')}]"
            text = (c.get("text") or "").strip()
            parts.append(f"{header}\n{text}")
        return "\n\n".join(parts)
