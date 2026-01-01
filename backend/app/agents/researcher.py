import faiss
import numpy as np
import json
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
from .base import BaseAgent
from app.core.paths import SLIDES_EXTRACTION_DIR, SLIDES_EMB_DIR

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
            
        return self._format_hits(hits)

    def _format_hits(self, hits: List[dict]) -> str:
        parts = []
        for i, c in enumerate(hits, 1):
            header = f"[SOURCE: {c.get('pdf_stem')} | Slide {c.get('slide_no')}]"
            text = (c.get("text") or "").strip()
            parts.append(f"{header}\n{text}")
        return "\n\n".join(parts)
