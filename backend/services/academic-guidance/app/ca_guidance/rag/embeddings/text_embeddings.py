"""Text-only embeddings for querying (avoids CLIP model loading)."""

import os
import logging
from typing import List
import numpy as np

# Disable multiprocessing for SentenceTransformer on macOS to avoid segfaults
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Set PyTorch to use single thread to avoid multiprocessing issues on macOS
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# Set torch threads before importing SentenceTransformer (which uses torch)
try:
    import torch
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
except ImportError:
    pass

from sentence_transformers import SentenceTransformer

from app.ca_guidance.rag.config.settings import TARGET_DIM

logger = logging.getLogger(__name__)


class TextEmbeddings:
    """Text-only embedding model for querying (no CLIP, avoids segfaults)."""
    
    def __init__(self, text_model_name: str, device="cpu"):
        """
        Initialize text-only embeddings model.
        
        Args:
            text_model_name: Name of the SentenceTransformer model
            device: Device to run models on ("cpu" or "cuda")
        """
        try:
            # Disable multiprocessing explicitly to avoid macOS segfaults
            self.text_model = SentenceTransformer(
                text_model_name, 
                device=device,
                model_kwargs={'local_files_only': False}
            )
            self.device = device
            
            txt_dim = self.text_model.get_sentence_embedding_dimension()
            
            # Generate projection matrix (keep as numpy array to avoid torch segfault on macOS)
            rng = np.random.RandomState(42)
            proj_matrix = rng.normal(size=(txt_dim, TARGET_DIM))
            self.txt_proj = proj_matrix.astype(np.float32)
        except Exception as e:
            logger.error(f"Failed to initialize TextEmbeddings: {e}", exc_info=True)
            raise

    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """
        Embed a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of numpy arrays with embeddings
        """
        # Use batch_size=1 and ensure no multiprocessing to avoid segfaults
        emb = self.text_model.encode(
            texts, 
            convert_to_numpy=True, 
            show_progress_bar=False,
            batch_size=1,
            normalize_embeddings=False  # We'll normalize after projection
        )
        # Project to TARGET_DIM and normalize
        emb_t = (emb @ self.txt_proj)
        emb_t = emb_t / (np.linalg.norm(emb_t, axis=1, keepdims=True) + 1e-12)
        return emb_t

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embed documents for LangChain compatibility.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of lists of floats (embeddings)
        """
        arr = self.embed_texts(texts)
        return arr.tolist()

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a single query string.
        
        Args:
            query: Query string to embed
            
        Returns:
            List of floats (embedding)
        """
        arr = self.embed_texts([query])[0]
        return arr.tolist()

