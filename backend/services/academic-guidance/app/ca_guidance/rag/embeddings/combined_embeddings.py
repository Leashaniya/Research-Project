"""Combined embeddings for text and images using SentenceTransformer and CLIP."""

from typing import List
import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import CLIPProcessor, CLIPModel
from PIL import Image

from app.ca_guidance.rag.config.settings import EMBED_DIM_IMAGE, TARGET_DIM


class CombinedEmbeddings:
    """Combined embedding model for text and images."""
    
    def __init__(self, text_model_name: str, image_model_name: str, device="cpu"):
        """
        Initialize combined embeddings model.
        
        Args:
            text_model_name: Name of the SentenceTransformer model
            image_model_name: Name of the CLIP model
            device: Device to run models on ("cpu" or "cuda")
        """
        # Text embedder
        self.text_model = SentenceTransformer(text_model_name, device=device)
        # Image embedder (CLIP)
        self.clip_model = CLIPModel.from_pretrained(image_model_name).to(device)
        self.clip_processor = CLIPProcessor.from_pretrained(image_model_name)
        self.device = device
        
        # Projection to TARGET_DIM if needed
        # For simplicity we'll create random projection matrices (you can replace with learned linear layers)
        txt_dim = self.text_model.get_sentence_embedding_dimension()
        img_dim = self.clip_model.visual_projection.out_features if hasattr(self.clip_model, "visual_projection") else EMBED_DIM_IMAGE
        
        # Create projection matrices (deterministic by seeding)
        rng = np.random.RandomState(42)
        self.txt_proj = torch.tensor(rng.normal(size=(txt_dim, TARGET_DIM)), dtype=torch.float32, device=device)
        self.img_proj = torch.tensor(rng.normal(size=(img_dim, TARGET_DIM)), dtype=torch.float32, device=device)

    def embed_texts(self, texts: List[str]) -> List[np.ndarray]:
        """
        Embed a list of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of numpy arrays with embeddings
        """
        emb = self.text_model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        # project to TARGET_DIM
        emb_t = (emb @ self.txt_proj.cpu().numpy())
        # normalize
        emb_t = emb_t / (np.linalg.norm(emb_t, axis=1, keepdims=True) + 1e-12)
        return emb_t

    def embed_images(self, image_paths: List[str]) -> List[np.ndarray]:
        """
        Embed a list of images.
        
        Args:
            image_paths: List of paths to image files
            
        Returns:
            List of numpy arrays with embeddings
        """
        imgs = []
        for p in image_paths:
            image = Image.open(p).convert("RGB")
            imgs.append(image)
        inputs = self.clip_processor(images=imgs, return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            outputs = self.clip_model.get_image_features(**inputs)  # shape (N, img_dim)
            img_feats = outputs.cpu().numpy()
        emb_i = img_feats @ self.img_proj.cpu().numpy()
        emb_i = emb_i / (np.linalg.norm(emb_i, axis=1, keepdims=True) + 1e-12)
        return emb_i

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

