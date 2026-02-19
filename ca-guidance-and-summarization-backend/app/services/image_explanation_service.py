"""Service for generating detailed explanations for images in summaries.

This service uses OpenAI Vision API to analyze images and LLM to generate
context-aware explanations that connect images to the topic being summarized.
"""

import logging
import base64
from pathlib import Path
from typing import Optional
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR, OPENAI_VISION_MODEL

logger = logging.getLogger(__name__)


class ImageExplanationService:
    """Service for generating image explanations using Vision API and LLM."""
    
    def __init__(self):
        self.vision_model = OPENAI_VISION_MODEL
        self.openai_client = None
        self.llm = None
    
    def _get_openai_client(self) -> OpenAI:
        """Lazy load OpenAI client."""
        if self.openai_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not configured")
            # Add timeout to prevent DNS/network hangs
            try:
                import httpx
                self.openai_client = OpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    timeout=httpx.Timeout(30.0, connect=10.0)  # 30s total, 10s connect timeout
                )
            except ImportError:
                # Fallback if httpx not available
                self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self.openai_client
    
    def _get_llm(self) -> ChatOpenAI:
        """Lazy load LLM for context-aware explanations."""
        if self.llm is None:
            self.llm = ChatOpenAI(
                model="gpt-4o-mini",
                api_key=settings.OPENAI_API_KEY,
                temperature=0.3,
                timeout=30.0  # 30 second timeout
            )
        return self.llm
    
    def _encode_image_to_base64(self, image_path: Path) -> str:
        """Encode image to base64 for OpenAI API."""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            raise
    
    def _analyze_image_with_vision(self, image_path: Path) -> str:
        """
        Analyze image using OpenAI Vision API to get detailed description.
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Detailed analysis of the image content
        """
        try:
            client = self._get_openai_client()
            base64_image = self._encode_image_to_base64(image_path)
            
            prompt = f"""Analyze THIS SPECIFIC IMAGE (filename: {image_path.name}) in EXTREME DETAIL and provide a comprehensive, unique description.

Provide a thorough analysis covering:
1. What type of diagram/image this SPECIFIC image is (ER diagram, flowchart, UML diagram, table, etc.) and its specific purpose
2. ALL main elements/components shown in THIS image (entities, attributes, relationships, etc.)
3. Detailed relationships and connections between elements in THIS image
4. ALL key labels, text, annotations, or symbols visible in THIS image
5. The overall purpose or concept being illustrated in THIS SPECIFIC image
6. Any unique features, patterns, constraints, or details that distinguish this image from others
7. The structure and organization of the diagram
8. Any important visual elements like colors, shapes, arrows, or formatting that convey meaning

Be EXTREMELY detailed and specific. This description will be used to generate a COMPREHENSIVE explanation for THIS SPECIFIC IMAGE for students learning about database management systems.
Each image is different - analyze THIS image's actual content in detail, not generic descriptions.
Aim for 300-500 words of detailed visual analysis."""

            response = client.chat.completions.create(
                model=self.vision_model,
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
                max_tokens=1000,  # Increased for very detailed analysis of visual aids
                temperature=0.2,
                timeout=30.0  # 30 second timeout
            )
            
            analysis = response.choices[0].message.content.strip()
            logger.info(f"✅ Vision API analysis completed for {image_path.name} ({len(analysis)} chars)")
            logger.debug(f"Vision analysis for {image_path.name}: {analysis[:200]}...")
            return analysis
            
        except Exception as e:
            error_msg = str(e)
            if "DNS" in error_msg or "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logger.error(f"Vision API network error (DNS/timeout) for {image_path.name}: {e}")
            else:
                logger.error(f"Vision API analysis failed for {image_path.name}: {e}")
            raise
    
    def generate_explanation(
        self,
        image_path: str,
        topic: Optional[str] = None,
        context_text: Optional[str] = None
    ) -> str:
        """
        Generate a context-aware explanation for an image.
        
        Args:
            image_path: Path to the image file (relative to IMAGE_OUTPUT_DIR or absolute)
            topic: The topic being summarized (for context)
            context_text: Optional additional context from the summary
            
        Returns:
            Formatted explanation text, or empty string if generation fails
        """
        try:
            # Resolve image path
            if Path(image_path).is_absolute():
                full_path = Path(image_path)
            else:
                full_path = IMAGE_OUTPUT_DIR / image_path
            
            if not full_path.exists():
                logger.warning(f"Image not found: {full_path}")
                return ""
            
            # Step 1: Analyze image with Vision API (with timeout handling)
            logger.info(f"🔍 Analyzing image with Vision API: {full_path.name} (path: {full_path})")
            try:
                vision_analysis = self._analyze_image_with_vision(full_path)
                logger.info(f"✅ Vision analysis completed for {full_path.name} ({len(vision_analysis)} chars)")
                logger.debug(f"Vision analysis preview for {full_path.name}: {vision_analysis[:150]}...")
            except Exception as vision_err:
                error_msg = str(vision_err)
                if "DNS" in error_msg or "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    logger.warning(f"Vision API skipped due to network error for {full_path.name}: {vision_err}")
                    return ""  # Return empty to skip explanation
                raise  # Re-raise other errors
            
            # Step 2: Generate context-aware explanation with LLM (with timeout handling)
            logger.info(f"🤖 Generating context-aware explanation for {full_path.name} using vision analysis ({len(vision_analysis)} chars)")
            try:
                explanation = self._generate_context_aware_explanation(
                    vision_analysis=vision_analysis,
                    topic=topic,
                    context_text=context_text,
                    image_name=full_path.name
                )
                logger.info(f"✅ Generated unique explanation for {full_path.name}: {explanation[:100]}..." if explanation else f"❌ Empty explanation for {full_path.name}")
                return explanation
            except Exception as llm_err:
                error_msg = str(llm_err)
                if "DNS" in error_msg or "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                    logger.warning(f"LLM explanation skipped due to network error for {full_path.name}: {llm_err}")
                    # Fallback to vision analysis only if available
                    return vision_analysis[:200] + "..." if len(vision_analysis) > 200 else vision_analysis
                raise  # Re-raise other errors
            
        except Exception as e:
            error_msg = str(e)
            if "DNS" in error_msg or "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                logger.warning(f"Image explanation skipped due to network error (DNS/timeout) for {image_path}: {e}")
            else:
                logger.error(f"Failed to generate explanation for {image_path}: {e}", exc_info=True)
            return ""  # Return empty string so summary generation continues
    
    def _generate_context_aware_explanation(
        self,
        vision_analysis: str,
        topic: Optional[str],
        context_text: Optional[str],
        image_name: str
    ) -> str:
        """
        Use LLM to generate a context-aware explanation based on vision analysis.
        
        Args:
            vision_analysis: Detailed analysis from Vision API
            topic: The topic being summarized
            context_text: Optional context from summary
            image_name: Name of the image file
            
        Returns:
            Formatted explanation text
        """
        try:
            llm = self._get_llm()
            
            # Build prompt for context-aware explanation
            prompt_parts = [
                f"Generate a COMPREHENSIVE, DETAILED educational explanation for THIS SPECIFIC VISUAL AID (filename: {image_name}).",
                f"This visual aid is designed to help students understand complex database concepts through visual representation.",
                f"Each visual aid in the summary is different and requires a unique, thorough explanation based on its actual content.",
                "",
                "=== DETAILED VISUAL ANALYSIS ===",
                vision_analysis,
                "",
                "IMPORTANT: This explanation must be EXTREMELY detailed and specific to THIS visual aid only.",
                "Focus on helping students understand every aspect of what they're seeing in this visual aid.",
                ""
            ]
            
            if topic:
                prompt_parts.extend([
                    f"Topic being summarized: {topic}",
                    "Connect THIS SPECIFIC IMAGE's content to this topic in your explanation.",
                    ""
                ])
            
            if context_text:
                prompt_parts.extend([
                    "Context from summary (for reference only - focus on the image analysis above):",
                    context_text[:500],  # Limit context length
                    ""
                ])
            
            prompt_parts.extend([
                "Requirements:",
                f"- Write an EXTENSIVE, COMPREHENSIVE explanation (8-12 sentences, 200-300 words) for THIS SPECIFIC VISUAL AID ({image_name})",
                "- This is a VISUAL AID designed to help students understand complex concepts - explain it thoroughly",
                "- Base your explanation ONLY on the Image Analysis provided above",
                "- Each visual aid is unique - do not use generic or repeated explanations",
                "- Structure your explanation as follows:",
                "  1. INTRODUCTION: Identify the type of visual aid (ER diagram, flowchart, etc.) and its primary educational purpose",
                "  2. MAIN COMPONENTS: Describe ALL key elements, entities, attributes, relationships, or components shown in detail",
                "  3. RELATIONSHIPS: Explain how the components connect, interact, or relate to each other",
                "  4. DETAILED ELEMENTS: Describe specific labels, annotations, symbols, constraints, or visual details",
                "  5. CONCEPTUAL MEANING: Explain what concepts, principles, or database design patterns this visual aid demonstrates",
                "  6. EDUCATIONAL VALUE: Connect it to the topic and explain what students should learn from this visual aid",
                "  7. PRACTICAL SIGNIFICANCE: Explain why understanding this visual aid is important for database design",
                "  8. KEY TAKEAWAYS: Summarize the main learning points students should remember",
                "- Use clear, educational language suitable for students learning database management systems",
                "- Be EXTREMELY thorough and detailed - students should fully understand the visual aid from your explanation alone",
                "- Include specific examples from the image (entity names, relationship types, attribute details, etc.)",
                "- Explain the visual conventions used (symbols, lines, shapes, etc.) and what they mean",
                "- Do not include phrases like 'This image shows' or 'In this diagram' - be direct",
                "- Make sure your explanation is specific to this visual aid and different from explanations for other images",
                "- Aim for 200-300 words of comprehensive, educational explanation",
                "",
                "Comprehensive explanation for this specific visual aid:"
            ])
            
            prompt = "\n".join(prompt_parts)
            
            # Invoke LLM to generate comprehensive explanation
            # ChatOpenAI will use default max_tokens (typically 4096 for gpt-4o-mini)
            # which is sufficient for our 200-300 word explanations
            response = llm.invoke([HumanMessage(content=prompt)])
            explanation = response.content if hasattr(response, "content") else str(response)
            
            # Clean up explanation
            explanation = explanation.strip()
            if explanation.startswith('"') and explanation.endswith('"'):
                explanation = explanation[1:-1]
            
            logger.info(f"✅ Generated UNIQUE explanation for {image_name} ({len(explanation)} chars)")
            logger.debug(f"Explanation for {image_name}: {explanation[:200]}...")
            return explanation
            
        except Exception as e:
            logger.error(f"LLM explanation generation failed: {e}", exc_info=True)
            # Fallback to vision analysis if LLM fails
            return vision_analysis[:200] + "..." if len(vision_analysis) > 200 else vision_analysis


# Global instance
_image_explanation_service: Optional[ImageExplanationService] = None


def get_image_explanation_service() -> ImageExplanationService:
    """Get or create the global image explanation service instance."""
    global _image_explanation_service
    if _image_explanation_service is None:
        _image_explanation_service = ImageExplanationService()
    return _image_explanation_service


def generate_image_explanation(
    image_path: str,
    topic: Optional[str] = None,
    context_text: Optional[str] = None
) -> str:
    """
    Convenience function to generate image explanation.
    
    Args:
        image_path: Path to image file
        topic: Topic being summarized
        context_text: Optional context from summary
        
    Returns:
        Explanation text or empty string if generation fails
    """
    service = get_image_explanation_service()
    return service.generate_explanation(image_path, topic, context_text)
