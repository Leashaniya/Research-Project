import base64
import json
import time
import random
from pathlib import Path
from app.core.config import settings
from app.core.llm_factory import get_llm_client

def encode_image(image_path_or_bytes):
    """Encodes an image to base64."""
    if isinstance(image_path_or_bytes, (str, Path)):
        with open(image_path_or_bytes, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    return base64.b64encode(image_path_or_bytes).decode('utf-8')

def retry_with_backoff(func, max_retries=5, initial_delay=1):
    """
    Retry a function with exponential backoff on exceptions.
    """
    def wrapper(*args, **kwargs):
        delay = initial_delay
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Check for rate limit error (usually 429) or generic API errors
                error_str = str(e).lower()
                if "rate limit" in error_str or "429" in error_str:
                    if i == max_retries - 1:
                        raise e
                    
                    sleep_time = delay + random.uniform(0, 0.5)
                    print(f"   ⚠️ Rate limit hit. Retrying in {sleep_time:.2f}s... (Attempt {i+1}/{max_retries})")
                    time.sleep(sleep_time)
                    delay *= 2  # Exponential backoff
                else:
                    raise e
    return wrapper

@retry_with_backoff
def _call_vlm(prompt, base64_image, detail="low", max_tokens=300):
    """Internal helper to call the VLM with retry logic."""
    client = get_llm_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}", 
                            "detail": detail
                        },
                    },
                ],
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=max_tokens
    )
    return json.loads(response.choices[0].message.content)

def analyze_exam_diagram(image_path, context_text: str = "") -> dict:
    """
    Analyzes an exam diagram to extract semantic intent.
    Returns: { "semantic_label": str, "student_action": str, "type": str }
    """
    base64_image = encode_image(image_path)
    
    context_instruction = ""
    if context_text:
        # Truncate context to avoid token limits (e.g., first 1000 chars of page)
        snippet = context_text[:1000].replace("\n", " ")
        context_instruction = f'\n    CONTEXT FROM PAGE: "{snippet}"\n    Use this context to confirm the diagram type (e.g. if text says "Figure 1: Demand Curve", label it as such).'

    prompt = f"""
    Analyze this exam image. It is a diagram from a computer science or technical exam.{context_instruction}
    Identify the "Semantic Label" (what is shown) and the likely "Student Action" (what they must do).
    
    Return strict JSON:
    {{
        "semantic_label": "e.g., ER Diagram of Hospital System",
        "student_action": "e.g., Map to Relational Schema",
        "type": "e.g., ER Diagram / Flowchart / Graph / SQL Table"
    }}
    """
    
    try:
        return _call_vlm(prompt, base64_image, detail="low", max_tokens=300)
    except Exception as e:
        print(f"Vision analysis failed after retries: {e}")
        return {"semantic_label": "Unknown Diagram", "student_action": "Analyze", "type": "Unknown"}

def analyze_slide_diagram(image_path) -> dict:
    """
    Analyzes a lecture slide diagram to extract detailed caption and description.
    Returns: { "caption": str }
    """
    base64_image = encode_image(image_path)
    
    prompt = """
    Analyze this lecture slide diagram. 
    Provide a "Dense Caption" - a detailed textual description of the concepts, relationships, and key information shown in the diagram. 
    The description should be optimized for semantic search and should capture all important details that would help someone understand what the diagram illustrates.
    
    Return strict JSON:
    {
        "caption": "Detailed description of the visualization, concepts, relationships, and key information shown..."
    }
    """
    
    try:
        # Use high detail for slides as they often contain text
        return _call_vlm(prompt, base64_image, detail="high", max_tokens=500)
    except Exception as e:
        print(f"Slide vision analysis failed after retries: {e}")
        return {"caption": "Analysis failed"}
