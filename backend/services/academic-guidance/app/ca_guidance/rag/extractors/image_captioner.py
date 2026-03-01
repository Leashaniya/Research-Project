"""Image captioning utilities for content-based naming using OpenAI Vision."""

import re
import base64
from pathlib import Path
from typing import Optional, List


class ImageCaptioner:
    """Image captioner using OpenAI Vision API for generating descriptive captions."""
    
    def __init__(self, openai_model: str = "gpt-4o", api_key: Optional[str] = None):
        """
        Initialize the image captioner.
        
        Args:
            openai_model: OpenAI vision model to use (e.g., "gpt-4o", "gpt-4-vision-preview")
            api_key: Optional OpenAI API key. If not provided, will use environment variable.
        """
        self.openai_model = openai_model
        self.api_key = api_key
        self._openai_client = None
    
    def _load_openai_client(self):
        """Lazy load OpenAI client."""
        if self._openai_client is None:
            try:
                from openai import OpenAI
                if self.api_key:
                    self._openai_client = OpenAI(api_key=self.api_key)
                else:
                    self._openai_client = OpenAI()
            except ImportError:
                raise ImportError("OpenAI package not installed. Install with: pip install openai")
            except Exception as e:
                raise Exception(f"Failed to initialize OpenAI client: {e}")
    
    def _encode_image_to_base64(self, image_path: str) -> str:
        """Encode image to base64 for OpenAI API."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def generate_caption(self, image_path: str, context_text: Optional[str] = None) -> str:
        """
        Generate caption using OpenAI Vision API.
        
        Args:
            image_path: Path to the image file
            context_text: Optional context from PDF
            
        Returns:
            Generated caption string
        """
        self._load_openai_client()
        
        try:
            # Encode image
            base64_image = self._encode_image_to_base64(image_path)
            
            # Build prompt - ask for concise but descriptive caption
            prompt_parts = [
                "Analyze this image and provide a concise, descriptive caption.",
                "The caption should be clear enough that someone can understand what the image shows without seeing it.",
                "",
                "If it's a diagram, include:",
                "- The diagram type (class diagram, sequence diagram, UML diagram, etc.)",
                "- The main design pattern or concept name (singleton, factory, observer, etc.)",
                "- Key distinguishing elements if needed for clarity",
                "",
                "If it's NOT a diagram (e.g., text, code, screenshot), describe what it is clearly.",
                "",
                "Be as concise as possible while remaining descriptive and informative.",
                "Examples: 'singleton pattern class diagram', 'factory method sequence diagram showing creation', 'code snippet with iterator pattern', 'text explanation of adapter pattern'",
                "",
                "Caption:"
            ]
            
            if context_text:
                prompt_parts.append(f"\nContext from document: {context_text[:200]}")
            
            prompt = "\n".join(prompt_parts)
            
            response = self._openai_client.chat.completions.create(
                model=self.openai_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=150,
                temperature=0.3  # Lower temperature for more consistent, factual descriptions
            )
            
            caption = response.choices[0].message.content.strip()
            return caption.lower().strip()
            
        except Exception as e:
            print(f"OpenAI captioning failed for {image_path}: {e}")
            return "diagram"
    
    @staticmethod
    def sanitize_for_filename(text: str, max_length: int = 50) -> str:
        """
        Sanitize OpenAI's caption to be used as a filename.
        Simply converts spaces to underscores and removes special characters.
        
        Args:
            text: Caption text from OpenAI (already concise, 2-4 words)
            max_length: Maximum length of the filename (excluding extension)
            
        Returns:
            Sanitized filename-safe string
        """
        if not text:
            return "image"
        
        # Convert to lowercase and replace spaces with underscores
        text = text.lower().strip()
        text = re.sub(r'\s+', '_', text)  # Replace spaces with underscores
        
        # Remove special characters, keep only alphanumeric and underscores
        text = re.sub(r'[^\w-]', '', text)
        text = text.strip('_-')
        
        # Truncate if too long
        if len(text) > max_length:
            text = text[:max_length].rstrip('_-')
        
        # Ensure it's not empty
        if not text:
            text = "image"
        
        return text
