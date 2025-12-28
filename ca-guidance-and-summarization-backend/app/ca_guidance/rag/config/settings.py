"""Configuration settings for the Multimodal RAG system."""

from pathlib import Path
import torch

# Directory paths - relative to the rag module directory
RAG_DIR = Path(__file__).parent.parent  # app/ca_guidance/rag/
LECTURES_DIR = RAG_DIR / "lectures"  # folder with PDFs
IMAGE_OUTPUT_DIR = RAG_DIR / "extracted_images"
IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
VECTORSTORE_DIR = RAG_DIR / "vectorstore"  # folder to save/load FAISS vectorstore
VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

# Model configuration
TEXT_EMBED_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"  # small & fast
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
IMAGE_MODEL_NAME = "openai/clip-vit-base-patch32"  # HuggingFace CLIP model id to use with transformers

# Embedding dimensions
EMBED_DIM_TEXT = 384  # depends on text model (all-MiniLM-L6-v2 -> 384)
EMBED_DIM_IMAGE = 512  # CLIP ViT-B/32 produces 512-dim image embeddings
# We'll concatenate or project to a single dimension; for simplicity we'll L2-normalize and concatenate then reduce to a single FAISS space by projecting to 512 (via linear map).
TARGET_DIM = 512

# Image filtering configuration (for diagram detection)
MIN_IMAGE_WIDTH = 150  # Minimum width in pixels
MIN_IMAGE_HEIGHT = 150  # Minimum height in pixels
MAX_ASPECT_RATIO = 15.0  # Maximum width/height ratio
MIN_ASPECT_RATIO = 0.1  # Minimum width/height ratio
MIN_FILE_SIZE = 5000  # Minimum file size in bytes

# Image captioning configuration (for content-based naming)
USE_CONTENT_BASED_NAMING = True  # Enable content-based image naming
OPENAI_VISION_MODEL = "gpt-4o"  # OpenAI vision model for image analysis (requires OPENAI_API_KEY)

