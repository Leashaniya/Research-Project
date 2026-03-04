"""
Bloom's Taxonomy Classifier  (from blooms.py / services.py)
"""

import pickle
from app.core.config import settings

_bloom_model = None


def _load_bloom_model():
    global _bloom_model
    if settings.BLOOM_MODEL_PATH.exists():
        try:
            with open(settings.BLOOM_MODEL_PATH, "rb") as f:
                _bloom_model = pickle.load(f)
            print(f"✓ Bloom model loaded from {settings.BLOOM_MODEL_PATH}")
        except Exception as e:
            print(f"✗ Failed to load Bloom model: {e}")


_load_bloom_model()


def classify_bloom_level(question: str) -> str:
    """Classify a question into easy / medium / hard using the trained SVM."""
    if _bloom_model is None:
        return "medium"
    return _bloom_model.predict([question])[0]
