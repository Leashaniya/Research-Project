"""
DALL·E Image Generation Service

Generates images from textual descriptions using OpenAI's DALL·E 3 API.
Used for creating diagrams and visual elements in generated exam questions.
"""

import os
import time
import random
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.config import settings
from app.core.llm_factory import get_llm_client


def retry_with_backoff(func, max_retries=3, initial_delay=2):
    """
    Retry a function with exponential backoff on exceptions.
    """
    def wrapper(*args, **kwargs):
        delay = initial_delay
        for i in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                if "rate limit" in error_str or "429" in error_str:
                    if i == max_retries - 1:
                        raise e
                    
                    sleep_time = delay + random.uniform(0, 1)
                    print(f"   ⚠️ DALL·E rate limit hit. Retrying in {sleep_time:.2f}s... (Attempt {i+1}/{max_retries})")
                    time.sleep(sleep_time)
                    delay *= 2  # Exponential backoff
                else:
                    raise e
    return wrapper


@retry_with_backoff
def generate_image_from_description(
    prompt: str,
    output_dir: Optional[Path] = None,
    question_no: Optional[str] = None,
    size: str = "1024x1024",
    quality: str = "standard",
    model: str = "dall-e-3"
) -> Dict[str, Any]:
    """
    Generate an image from a textual description using OpenAI's DALL·E 3 API.
    
    Args:
        prompt: Textual description of the image to generate
        output_dir: Directory to save the image (default: data/outputs/model_papers/images/)
        question_no: Question number for filename (e.g., "Q1")
        size: Image size ("1024x1024", "1792x1024", or "1024x1792")
        quality: Image quality ("standard" or "hd")
        model: DALL·E model to use ("dall-e-3" or "dall-e-2")
    
    Returns:
        Dictionary with:
        - "success": bool
        - "image_url": str (URL from OpenAI, temporary)
        - "image_path": str (local file path if saved)
        - "image_base64": str (base64 encoded image data, optional)
        - "error": str (error message if failed)
    """
    try:
        client = get_llm_client()
        
        # Validate API key
        if not settings.OPENAI_API_KEY:
            raise ValueError("OpenAI API Key is missing. Cannot generate images.")
        
        # Build the prompt for DALL·E
        # Enhance prompt for technical diagrams
        enhanced_prompt = _enhance_diagram_prompt(prompt)
        
        print(f"   🎨 Generating image with DALL·E 3: {enhanced_prompt[:100]}...")
        
        # Call DALL·E API
        # Note: DALL·E 3 only supports n=1, quality and size are specific to DALL·E 3
        if model == "dall-e-3":
            response = client.images.generate(
                model=model,
                prompt=enhanced_prompt,
                size=size,
                quality=quality,
                n=1,  # DALL·E 3 only supports n=1
                response_format="url"  # Get URL, we'll download it
            )
        else:
            # DALL·E 2 (fallback, if needed)
            response = client.images.generate(
                model=model,
                prompt=enhanced_prompt,
                size=size,
                n=1,
                response_format="url"
            )
        
        image_url = response.data[0].url
        
        # Download and save the image
        image_path = None
        image_base64 = None
        
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Download image from URL
            img_response = requests.get(image_url, timeout=30)
            img_response.raise_for_status()
            
            # Generate filename
            timestamp = int(time.time())
            filename = f"{question_no or 'diagram'}_{timestamp}.png"
            image_path = output_dir / filename
            
            # Save image
            with open(image_path, "wb") as f:
                f.write(img_response.content)
            
            print(f"   ✅ Image saved to: {image_path}")
        
        return {
            "success": True,
            "image_url": image_url,
            "image_path": str(image_path) if image_path else None,
            "image_base64": None,  # Can be added if needed
            "prompt_used": enhanced_prompt
        }
        
    except Exception as e:
        error_msg = str(e)
        print(f"   ❌ DALL·E image generation failed: {error_msg}")
        return {
            "success": False,
            "image_url": None,
            "image_path": None,
            "image_base64": None,
            "error": error_msg,
            "prompt_used": prompt
        }


def _enhance_diagram_prompt(prompt: str) -> str:
    """
    Enhance the prompt for better DALL·E results, especially for technical diagrams.
    
    Args:
        prompt: Original prompt text
    
    Returns:
        Enhanced prompt optimized for DALL·E
    """
    prompt_lower = prompt.lower()
    
    # Detect diagram type and enhance accordingly
    if "er diagram" in prompt_lower or "eer diagram" in prompt_lower or "entity relationship" in prompt_lower:
        enhanced = f"A clear, professional Entity-Relationship (ER) diagram showing database entities, attributes, and relationships. {prompt} Technical diagram style, black and white or minimal colors, suitable for academic exam paper."
    elif "normalization" in prompt_lower or "normal form" in prompt_lower:
        enhanced = f"A clear, professional database normalization diagram showing relation schemas and functional dependencies. {prompt} Technical diagram style, black and white or minimal colors, suitable for academic exam paper."
    elif "sql" in prompt_lower or "query" in prompt_lower:
        enhanced = f"A clear, professional SQL query diagram or database schema visualization. {prompt} Technical diagram style, black and white or minimal colors, suitable for academic exam paper."
    elif "transaction" in prompt_lower or "schedule" in prompt_lower:
        enhanced = f"A clear, professional database transaction schedule diagram showing operations and dependencies. {prompt} Technical diagram style, black and white or minimal colors, suitable for academic exam paper."
    elif "tree" in prompt_lower or "b-tree" in prompt_lower or "index" in prompt_lower:
        enhanced = f"A clear, professional database index tree diagram (B-tree or similar). {prompt} Technical diagram style, black and white or minimal colors, suitable for academic exam paper."
    else:
        # Generic enhancement for other diagrams
        enhanced = f"A clear, professional technical diagram. {prompt} Academic exam paper style, black and white or minimal colors, suitable for database systems course."
    
    return enhanced


def generate_diagram_for_question(
    question_text: str,
    subquestion_text: Optional[str] = None,
    diagram_type: Optional[str] = None,
    question_no: Optional[str] = None,
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Generate a diagram for a question based on the question text and diagram type.
    
    Args:
        question_text: Main question text/stem
        subquestion_text: Specific sub-question text that mentions the diagram
        diagram_type: Type of diagram ("ER", "EER", "Normalization", "SQL", etc.)
        question_no: Question number for filename
        output_dir: Directory to save the image
    
    Returns:
        Dictionary with image generation result
    """
    # Build prompt from question context
    if subquestion_text:
        # Use sub-question text if it specifically mentions the diagram
        prompt = subquestion_text
    else:
        # Use main question text
        prompt = question_text
    
    # Add diagram type context if available
    if diagram_type:
        if diagram_type.upper() in ["ER", "EER"]:
            prompt = f"Draw an {diagram_type} diagram: {prompt}"
        elif diagram_type == "Normalization":
            prompt = f"Show normalization process: {prompt}"
        else:
            prompt = f"Create a {diagram_type} diagram: {prompt}"
    
    # Set default output directory if not provided
    if output_dir is None:
        from app.core.paths import OUTPUTS_DIR
        output_dir = OUTPUTS_DIR / "model_papers" / "images"
    
    return generate_image_from_description(
        prompt=prompt,
        output_dir=output_dir,
        question_no=question_no,
        size="1024x1024",
        quality="standard"
    )
