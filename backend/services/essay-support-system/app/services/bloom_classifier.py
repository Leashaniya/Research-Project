"""
Bloom's Taxonomy Classifier  (from blooms.py / services.py)
"""

import pickle
from app.core.config import settings
from app.services.evaluation_service import get_openai_client

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


def _classify_with_openai(question: str) -> str | None:
    client = get_openai_client()
    if not client:
        return None

    allowed = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
    prompt = (
        "Classify the question into one Bloom level: remember, understand, apply, analyze, evaluate, or create. "
        "Reply with only the single level word.\n\n"
        f"Question: {question}"
    )
    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You assign Bloom taxonomy levels."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=5,
        )
        text = (resp.choices[0].message.content or "").strip().lower()
        token = text.split()[0] if text else ""
        return token if token in allowed else None
    except Exception as e:
        print(f"✗ OpenAI Bloom classify error: {e}")
        return None


def classify_bloom_level(question: str) -> str:
    """Classify a question into difficulty using trained model first, OpenAI as fallback."""
    # Try local trained model first
    if _bloom_model is not None:
        try:
            # The trained model predicts difficulty directly (easy/medium/hard)
            difficulty = _bloom_model.predict([question])[0]
            print(f"✓ Local model classified as: {difficulty}")
            return difficulty
        except Exception as e:
            print(f"✗ Local model prediction failed: {e}")
    
    # Fallback to OpenAI if local model fails or isn't available
    print("⚠ Falling back to OpenAI for classification")
    llm_level = _classify_with_openai(question)
    if llm_level:
        # Convert OpenAI's Bloom level to difficulty
        return map_bloom_to_difficulty(llm_level)
    
    # Final fallback
    return "medium"


def map_bloom_to_difficulty(bloom_level: str) -> str:
    """Map Bloom's taxonomy level to difficulty category."""
    bloom_level = bloom_level.lower().strip()
    
    # Easy: Remember, Understand
    if bloom_level in ["remember", "understand"]:
        return "easy"
    # Medium: Apply, Analyze  
    elif bloom_level in ["apply", "analyze"]:
        return "medium"
    # Hard: Evaluate, Create
    elif bloom_level in ["evaluate", "create"]:
        return "hard"
    else:
        # Fallback for unknown levels
        return "medium"
