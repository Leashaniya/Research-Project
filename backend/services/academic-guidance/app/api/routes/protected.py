import fitz  # PyMuPDF
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.schemas import (
    UserInfo, 
    SummarizeRequest,
    SummaryFeedbackRequest,
    ReinforceSummaryRequest,
    SummaryResponse,
    FeedbackResponse,
    SaveFlashcardSetRequest,
    FlashcardFeedbackRequest,
    FlashcardUpdateRequest,
    GuidanceFeedbackRequest,
    ReinforceGuidanceRequest,
)
from app.ca_guidance.crew import create_guidance_crew, create_summarization_crew
from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR
from app.ca_guidance.tools.tts_tool import text_to_speech_wav  # ✅ AUDIO
from app.ca_guidance.tools.rag_tool import (
    _get_rag_chain,
    _extract_context_text,
    _verify_summary_accuracy,
    verify_guidance_accuracy
)

logger = logging.getLogger(__name__)


def _effective_audio_url(summary_doc: dict) -> Optional[str]:
    """Return audio URL for a summary: prefer GridFS endpoint when audio is stored there."""
    if not summary_doc:
        return None
    # If we have audio in GridFS, use the stream endpoint (works even if static file is missing)
    if summary_doc.get("audio_file_id"):
        return f"/protected/summaries/{summary_doc['_id']}/audio"
    return summary_doc.get("audio_url")


def extract_and_replace_images(
    content: str, 
    base_url: str = "/api/images/",
    topic: Optional[str] = None,
    generate_explanations: bool = True,
    context_text: Optional[str] = None
) -> tuple[str, list[str]]:
    """
    Extract image references from markdown and replace with proper image tags.
    Optionally generates explanations below each image.
    
    Args:
        content: Markdown content with [IMAGE:...] references
        base_url: Base URL for image paths
        topic: Topic being summarized (for context-aware explanations)
        generate_explanations: Whether to generate explanations for images
        context_text: Optional context text from summary for better explanations
        
    Returns:
        Tuple of (cleaned_content with images and explanations, list_of_image_paths)
    """
    if not content:
        return content, []

    image_paths = []
    image_counter = [0]  # Use list to allow modification in nested function

    # Normalize content: Handle [IMAGE:...], ![alt](IMAGE:...), and ![alt](filename.png) formats
    # Also handle cases where image names are split across lines
    def normalize_image_refs(text):
        # First, handle markdown image syntax: ![alt](IMAGE:filename) - handles multiline
        def fix_markdown_image(match):
            alt_text = match.group(1) if match.group(1) else ""
            img_content = match.group(2)
            # Remove newlines and normalize whitespace
            img_content = re.sub(r'\s+', '', img_content)
            return f'[IMAGE:{img_content}]'
        
        # Replace ![alt](IMAGE:filename) with [IMAGE:filename] - handles multiline alt/text
        # Pattern matches: ![anything](IMAGE:anything) even if split across lines
        # Use non-greedy matching and DOTALL to handle multiline content
        text = re.sub(
            r'!\[([^\]]*?)\]\(\s*IMAGE:\s*([^\)]+?)\s*\)',
            fix_markdown_image,
            text,
            flags=re.DOTALL | re.MULTILINE
        )
        
        # Also handle case where IMAGE: might be lowercase: ![alt](image:filename)
        text = re.sub(
            r'!\[([^\]]*?)\]\(\s*image:\s*([^\)]+?)\s*\)',
            fix_markdown_image,
            text,
            flags=re.DOTALL | re.MULTILINE | re.IGNORECASE
        )
        
        # CRITICAL: Handle plain markdown image syntax: ![alt](filename.png)
        # This is what CrewAI is outputting - plain markdown without IMAGE: prefix
        # Only match if it looks like an image filename (has image extension and doesn't start with http/https)
        def fix_plain_markdown_image(match):
            alt_text = match.group(1) if match.group(1) else ""
            img_content = match.group(2)
            # Remove newlines and normalize whitespace
            img_content = re.sub(r'\s+', '', img_content)
            
            # Skip if it already has IMAGE: prefix (should have been processed already, but double-check)
            if 'IMAGE:' in img_content.upper():
                return match.group(0)
            
            # Only convert if it looks like an image filename (has image extension and is not a URL)
            img_content_lower = img_content.lower()
            if (re.search(r'\.(png|jpg|jpeg|gif|webp)$', img_content, re.IGNORECASE) and 
                not img_content_lower.startswith(('http://', 'https://', '//')) and
                not img_content.startswith('/')):
                logger.info(f"Converting plain markdown image to [IMAGE:...]: {img_content[:50]}...")
                return f'[IMAGE:{img_content}]'
            # Otherwise, leave it as-is (might be a URL or other link)
            return match.group(0)
        
        # Match ALL markdown images first, then filter in the function
        # This handles multiline cases better than trying to exclude URLs in the regex
        # Note: Images with IMAGE: prefix should already be converted above, but we check anyway
        text = re.sub(
            r'!\[([^\]]*?)\]\(\s*([^\)]+?)\s*\)',
            fix_plain_markdown_image,
            text,
            flags=re.DOTALL | re.MULTILINE
        )
        
        # Then normalize [IMAGE:...] patterns (remove newlines/whitespace inside)
        # This handles cases where [IMAGE:filename] is split across lines
        def fix_ref(match):
            img_content = match.group(1)
            # Remove ALL whitespace including newlines, tabs, spaces
            img_content = re.sub(r'\s+', '', img_content)
            logger.debug(f"Normalized image reference: {img_content[:80]}...")
            return f'[IMAGE:{img_content}]'
        # Use DOTALL to match across newlines, and make it non-greedy
        text = re.sub(r'\[IMAGE:([^\]]+?)\]', fix_ref, text, flags=re.DOTALL)
        
        return text
    
    # Log original content for debugging - check for both IMAGE: prefix and plain markdown
    original_image_refs_with_prefix = re.findall(r'!\[([^\]]*?)\]\(\s*IMAGE:\s*([^\)]+?)\s*\)', content, flags=re.DOTALL | re.MULTILINE)
    original_plain_image_refs = re.findall(r'!\[([^\]]*?)\]\(\s*([^\)]+?\.(?:png|jpg|jpeg|gif|webp))\s*\)', content, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)
    if original_image_refs_with_prefix:
        logger.info(f"Found {len(original_image_refs_with_prefix)} markdown image reference(s) with IMAGE: prefix before normalization")
    if original_plain_image_refs:
        logger.info(f"Found {len(original_plain_image_refs)} plain markdown image reference(s) (without IMAGE: prefix) before normalization: {[ref[1][:50] for ref in original_plain_image_refs[:3]]}")
    
    # Normalize image references first
    content = normalize_image_refs(content)

    # Pattern to match [IMAGE:...] (after normalization)
    image_pattern = r'\[IMAGE:([^\]]+)\]'
    
    # Log image references found in content after normalization
    image_matches = re.findall(image_pattern, content)
    if image_matches:
        logger.info(f"✅ Found {len(image_matches)} image reference(s) in content after normalization:")
        for i, img_match in enumerate(image_matches[:5], 1):
            logger.info(f"   {i}. [IMAGE:{img_match[:80]}...]")
    else:
        logger.warning("⚠ No [IMAGE:...] references found in content after normalization!")
        logger.debug(f"Content preview (first 500 chars): {content[:500]}")

    available_images = {}
    if IMAGE_OUTPUT_DIR.exists():
        for img_file in IMAGE_OUTPUT_DIR.glob("*"):
            if img_file.is_file() and img_file.suffix.lower() in ['.jpeg', '.jpg', '.png', '.gif']:
                available_images[img_file.name] = img_file.name
                available_images[img_file.name.lower()] = img_file.name
        
        logger.info(f"Found {len(available_images)} available image(s) in {IMAGE_OUTPUT_DIR}")
        if image_matches and len(available_images) > 0:
            logger.info(f"Sample available images: {list(available_images.keys())[:5]}")
    else:
        logger.warning(f"IMAGE_OUTPUT_DIR does not exist: {IMAGE_OUTPUT_DIR}")

    def replace_image(match):
        img_name = match.group(1).strip()
        import urllib.parse
        
        logger.debug(f"Processing image reference: '{img_name[:80]}...'")

        actual_name = None
        # First try exact match
        if img_name in available_images:
            actual_name = available_images[img_name]
            logger.debug(f"Exact match found: {actual_name}")
        elif img_name.lower() in available_images:
            actual_name = available_images[img_name.lower()]
            logger.debug(f"Case-insensitive exact match found: {actual_name}")
        else:
            # Try partial matching for long filenames that might be split across lines
            img_name_lower = img_name.lower().replace('_', '').replace('-', '')
            logger.debug(f"Trying partial match for: {img_name_lower[:50]}...")
            for available_name in available_images.values():
                available_name_normalized = available_name.lower().replace('_', '').replace('-', '')
                # Check if the image name is contained in the available name or vice versa
                if (img_name_lower in available_name_normalized or 
                    available_name_normalized.startswith(img_name_lower) or
                    img_name_lower.startswith(available_name_normalized[:len(img_name_lower)])):
                    actual_name = available_name
                    logger.info(f"Partial match found: '{img_name[:50]}...' -> '{actual_name}'")
                    break
        
        if actual_name:
            image_paths.append(actual_name)
            encoded_name = urllib.parse.quote(actual_name)
            image_markdown = f'![{actual_name}]({base_url}{encoded_name})'
            logger.info(f"Matched image '{img_name[:50]}...' -> '{actual_name}', URL: {base_url}{encoded_name}")
            
            # Generate explanation if enabled
            logger.info(f"🔍 Explanation generation check: generate_explanations={generate_explanations} for image: {actual_name}")
            if generate_explanations:
                logger.info(f"✓ Explanation generation ENABLED - proceeding for image: {actual_name}")
                try:
                    from app.services.image_explanation_service import generate_image_explanation
                    logger.info(f"📝 Calling generate_image_explanation for: {actual_name}")
                    logger.info(f"   Image path: {actual_name}, Topic: {topic}, Context length: {len(context_text) if context_text else 0}")
                    explanation = generate_image_explanation(
                        image_path=actual_name,
                        topic=topic,
                        context_text=context_text
                    )
                    logger.info(f"📝 Explanation result for {actual_name}: {'SUCCESS' if explanation else 'EMPTY'} (length: {len(explanation) if explanation else 0})")
                    if explanation:
                        logger.info(f"   Explanation preview for {actual_name}: {explanation[:150]}...")
                    else:
                        logger.warning(f"   ⚠ No explanation generated for {actual_name} - will use basic caption")
                    
                    if explanation and explanation.strip():
                        image_counter[0] += 1
                        figure_num = image_counter[0]
                        # Use HTML figure/caption with pure HTML img tag (not markdown syntax)
                        logger.info(f"✓ Added explanation ({len(explanation)} chars) for image {figure_num}: {actual_name}")
                        logger.debug(f"Explanation preview: {explanation[:100]}...")
                        html_output = f'<figure>\n<img src="{base_url}{encoded_name}" alt="{actual_name}" class="markdown-image" />\n<figcaption><strong>Figure {figure_num}:</strong> {explanation}</figcaption>\n</figure>'
                        logger.info(f"Generated HTML figure tag for image {figure_num} (length: {len(html_output)} chars)")
                        return html_output
                    else:
                        logger.warning(f"✗ No explanation generated (empty result) for {actual_name} - using basic caption fallback")
                        # ALWAYS show a caption - generate basic caption from filename
                        image_counter[0] += 1
                        figure_num = image_counter[0]
                        # Generate a basic caption from filename if explanation failed
                        basic_caption = actual_name.replace('_', ' ').replace('-', ' ').replace('.png', '').replace('.jpg', '').replace('.jpeg', '').title()
                        basic_caption = ' '.join(basic_caption.split()[:10])  # Limit to first 10 words
                        logger.info(f"Using basic caption for image {figure_num}: {basic_caption[:50]}...")
                        html_output = f'<figure>\n<img src="{base_url}{encoded_name}" alt="{actual_name}" class="markdown-image" />\n<figcaption><strong>Figure {figure_num}:</strong> {basic_caption}</figcaption>\n</figure>'
                        logger.info(f"Generated HTML figure tag with basic caption for image {figure_num} (length: {len(html_output)} chars)")
                        return html_output
                except Exception as e:
                    error_msg = str(e)
                    # Don't fail summary generation if image explanation fails due to network issues
                    if "DNS" in error_msg or "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
                        logger.warning(f"Image explanation skipped due to network error for {actual_name}: {e}")
                    else:
                        logger.error(f"Failed to generate explanation for {actual_name}: {e}", exc_info=True)
                    # ALWAYS return HTML figure tag with basic caption, even on error
                    image_counter[0] += 1
                    figure_num = image_counter[0]
                    basic_caption = actual_name.replace('_', ' ').replace('-', ' ').replace('.png', '').replace('.jpg', '').replace('.jpeg', '').title()
                    basic_caption = ' '.join(basic_caption.split()[:10])  # Limit to first 10 words
                    logger.info(f"Using basic caption fallback for image {figure_num} after error: {basic_caption[:50]}...")
                    html_output = f'<figure>\n<img src="{base_url}{encoded_name}" alt="{actual_name}" class="markdown-image" />\n<figcaption><strong>Figure {figure_num}:</strong> {basic_caption}</figcaption>\n</figure>'
                    return html_output
            else:
                # Even when explanations are disabled, wrap in figure tag for consistency
                image_counter[0] += 1
                figure_num = image_counter[0]
                basic_caption = actual_name.replace('_', ' ').replace('-', ' ').replace('.png', '').replace('.jpg', '').replace('.jpeg', '').title()
                basic_caption = ' '.join(basic_caption.split()[:10])  # Limit to first 10 words
                logger.info(f"Explanations disabled - using basic caption for image {figure_num}: {basic_caption[:50]}...")
                html_output = f'<figure>\n<img src="{base_url}{encoded_name}" alt="{actual_name}" class="markdown-image" />\n<figcaption><strong>Figure {figure_num}:</strong> {basic_caption}</figcaption>\n</figure>'
                return html_output

        logger.error(f"❌ Image '{img_name[:50]}...' NOT FOUND in available images!")
        logger.error(f"   Searched for: {img_name}")
        logger.error(f"   Available images ({len(available_images)}): {list(available_images.keys())[:10]}")
        logger.warning(f"   Will generate HTML with placeholder - image may not display correctly")
        # Still generate HTML figure tag even if image not found, so explanation can be shown
        image_counter[0] += 1
        figure_num = image_counter[0]
        encoded_name = urllib.parse.quote(img_name)
        # Try to generate explanation even if image file not found (might work if path is slightly different)
        explanation_text = f"Image: {img_name.replace('_', ' ').replace('-', ' ').title()}"
        if generate_explanations:
            try:
                from app.services.image_explanation_service import generate_image_explanation
                # Try with the img_name as-is, in case the file exists with a slightly different name
                temp_explanation = generate_image_explanation(
                    image_path=img_name,
                    topic=topic,
                    context_text=context_text
                )
                if temp_explanation and temp_explanation.strip():
                    explanation_text = temp_explanation
                    logger.info(f"✓ Generated explanation for unmatched image: {img_name[:50]}...")
            except Exception as e:
                logger.debug(f"Could not generate explanation for unmatched image: {e}")
        html_output = f'<figure>\n<img src="{base_url}{encoded_name}" alt="{img_name}" class="markdown-image" onerror="this.style.display=\'none\'" />\n<figcaption><strong>Figure {figure_num}:</strong> {explanation_text}</figcaption>\n</figure>'
        return html_output

    cleaned_content = re.sub(image_pattern, replace_image, content)
    final_image_paths = list(set(image_paths))
    logger.info(f"Image extraction complete: {len(final_image_paths)} image(s) processed: {final_image_paths[:3]}...")
    
    # Verify HTML figure tags are in the content
    figure_count = cleaned_content.count('<figure>')
    figcaption_count = cleaned_content.count('<figcaption>')
    img_count = cleaned_content.count('<img')
    logger.info(f"📊 HTML verification: Found {figure_count} <figure> tags, {figcaption_count} <figcaption> tags, and {img_count} <img> tags in final content")
    
    if figure_count > 0:
        # Log a sample of the HTML to verify it's correct
        import re as re_module
        figure_matches = re_module.findall(r'<figure>.*?</figure>', cleaned_content, flags=re_module.DOTALL)
        if figure_matches:
            logger.info(f"✅ Sample figure HTML (first 400 chars): {figure_matches[0][:400]}...")
            # Check for explanations in figcaption
            figcaption_matches = re_module.findall(r'<figcaption>.*?</figcaption>', cleaned_content, flags=re_module.DOTALL)
            if figcaption_matches:
                logger.info(f"✅ Found {len(figcaption_matches)} figcaption tags with descriptions")
                for i, caption in enumerate(figcaption_matches[:3], 1):
                    caption_text = re_module.sub(r'<[^>]+>', '', caption)  # Remove HTML tags for preview
                    logger.info(f"   Caption {i} preview: {caption_text[:150]}...")
            # Also check img src attributes
            img_src_matches = re_module.findall(r'<img[^>]+src=["\']([^"\']+)["\']', cleaned_content)
            if img_src_matches:
                logger.info(f"✅ Found {len(img_src_matches)} img src attributes: {img_src_matches[:3]}")
                # Verify all images have /api/images/ prefix
                for src in img_src_matches:
                    if not src.startswith('/api/images/'):
                        logger.warning(f"⚠ Image src missing /api/images/ prefix: {src}")
    else:
        logger.warning(f"⚠ No figure tags found in content!")
    
    if figure_count == 0 and len(image_matches) > 0:
        logger.error(f"❌ CRITICAL: {len(image_matches)} images were matched but NO figure tags were generated!")
        logger.error(f"Content preview (first 1000 chars): {cleaned_content[:1000]}")
    
    if figure_count > 0 and figcaption_count == 0:
        logger.warning(f"⚠ WARNING: Found {figure_count} figure tags but NO figcaption tags! Images may not have descriptions.")
    
    if figure_count != figcaption_count:
        logger.warning(f"⚠ WARNING: Mismatch - {figure_count} figures but {figcaption_count} figcaptions!")
    
    return cleaned_content, final_image_paths


def clean_markdown_response(content: str) -> str:
    """
    Clean up markdown response by removing debug messages and tool call information.
    """
    if not content:
        return content

    lines = content.split('\n')
    cleaned_lines = []
    skip_next_empty = False

    for line in lines:
        if re.search(r'Running:\s*transfer_task_to_\w+', line):
            skip_next_empty = True
            continue

        if re.match(r'^[\s-]*Running:\s*$', line):
            skip_next_empty = True
            continue

        if 'expected_output=...' in line or 'task_description=...' in line or 'additional_information=...' in line:
            skip_next_empty = True
            continue

        if skip_next_empty and line.strip() == '':
            skip_next_empty = False
            continue

        skip_next_empty = False
        cleaned_lines.append(line)

    content = '\n'.join(cleaned_lines)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


router = APIRouter(prefix="/protected", tags=["protected"])


@router.post("/run-guidance")
async def run_guidance(
    user: UserInfo = Depends(get_current_user),
    file: UploadFile = File(...)
):
    logger.info("=== Starting guidance process ===")

    logger.info("Step 1: Extracting text from PDF")
    try:
        pdf_bytes = await file.read()
        text = ""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        logger.info(f"Extracted {len(text)} characters from PDF")

        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract any text from the uploaded PDF."
            )
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PDF file: {e}"
        )

    logger.info("Step 2: Creating and running CrewAI crew")
    try:
        crew = create_guidance_crew(
            assignment_text=text,
            access_token=user.access_token
        )

        logger.info("Step 3: Executing crew tasks")
        result = crew.kickoff()

        logger.info("Step 4: Extracting markdown from crew result")
        report_content = None

        if hasattr(result, 'raw'):
            report_content = result.raw
        elif hasattr(result, 'content'):
            report_content = result.content
        elif hasattr(result, 'tasks_output'):
            if result.tasks_output:
                last_task_output = result.tasks_output[-1]
                report_content = last_task_output.raw if hasattr(last_task_output, 'raw') else str(last_task_output)
        elif isinstance(result, str):
            report_content = result
        else:
            report_content = str(result)

        if not report_content:
            logger.error("Failed to extract markdown from crew result")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract markdown report from crew result"
            )

        report_str = str(report_content)
        cleaned_content = clean_markdown_response(report_str)

        base_url = "/api/images/"
        # For guidance, explanations are optional (set to False by default)
        final_content, image_paths = extract_and_replace_images(
            cleaned_content, 
            base_url=base_url,
            topic=None,  # Guidance doesn't have a specific topic
            generate_explanations=False,  # Disable for guidance to keep it focused
            context_text=None
        )

        logger.info(f"Successfully extracted markdown (length: {len(final_content)})")
        logger.info(f"Found {len(image_paths)} image(s) in response")

        # Store base guidance for reinforcement flow (same style as summarization)
        try:
            from app.services.guidance_reinforcement_service import GuidanceReinforcementService
            svc = GuidanceReinforcementService()
            guidance_id = svc.store_base_guidance(
                report_text=final_content,
                images=image_paths,
                user_email=user.email,
            )
            logger.info(f"Stored base guidance (id: {guidance_id})")
        except Exception as store_err:
            logger.warning(f"Failed to store base guidance for reinforcement: {store_err}")
            guidance_id = None

        logger.info("=== Guidance process completed ===")

        return {
            "report": final_content,
            "images": image_paths,
            "guidance_id": guidance_id,
        }

    except Exception as e:
        logger.error(f"Error running guidance manager: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run guidance: {e}"
        )


@router.post("/summarize")
async def summarize_topic(
    request: SummarizeRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Create a comprehensive summary of a topic from lecture materials.
    
    Behavior:
    - Checks for existing reinforced summary first (returns if found)
    - Otherwise checks for latest base summary (returns if found)
    - Otherwise generates new summary and stores it
    
    Returns:
        JSON response with summary, related images, audio_url, and summary_id
    """
    topic = request.topic.strip()
    force = request.force
    logger.info(f"=== Starting summarization for topic: {topic} (force={force}) ===")

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty."
        )

    try:
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        
        # Check for existing summary if not forcing regeneration
        if not force:
            existing_summary = service.get_latest_summary(topic, prefer_reinforced=True, user_email=user.email)
            
            if existing_summary:
                logger.info(f"Found existing {existing_summary['summary_type']} summary for topic '{topic}'")
                # Check if existing summary has figure tags (explanations)
                existing_content = existing_summary["summary_text"]
                has_figures = "<figure>" in existing_content if existing_content else False
                logger.info(f"Existing summary has figure tags: {has_figures}")
                return {
                    "summary": existing_content,
                    "images": existing_summary.get("images", []),
                    "topic": topic,
                    "audio_url": _effective_audio_url(existing_summary),
                    "summary_id": existing_summary["_id"],
                    "summary_type": existing_summary["summary_type"],
                    "created_at": existing_summary.get("created_at").isoformat() if existing_summary.get("created_at") else None,
                    "audio_duration_seconds": existing_summary.get("audio_duration_seconds"),
                    "from_cache": True
                }
        
        # Generate new summary
        logger.info("Step 1: Creating and running summarization crew")
        crew = create_summarization_crew(topic=topic)

        logger.info("Step 2: Executing summarization task")
        result = crew.kickoff()

        logger.info("Step 3: Extracting summary from crew result")
        summary_content = None

        if hasattr(result, 'raw'):
            summary_content = result.raw
        elif hasattr(result, 'content'):
            summary_content = result.content
        elif hasattr(result, 'tasks_output'):
            if result.tasks_output:
                last_task_output = result.tasks_output[-1]
                summary_content = last_task_output.raw if hasattr(last_task_output, 'raw') else str(last_task_output)
        elif isinstance(result, str):
            summary_content = result
        else:
            summary_content = str(result)

        if not summary_content:
            logger.error("Failed to extract summary from crew result")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract summary from crew result"
            )

        summary_str = str(summary_content)
        cleaned_content = clean_markdown_response(summary_str)
        
        # Log to check if image references are in the content
        if "[IMAGE:" in cleaned_content:
            logger.info(f"Found [IMAGE:...] references in cleaned summary content")
        else:
            logger.warning(f"No [IMAGE:...] references found in cleaned summary content. Content length: {len(cleaned_content)}")
            # Try to extract images from the tool result if available
            # (CrewAI might have the tool result with images)
            if hasattr(result, 'tasks_output') and result.tasks_output:
                for task_output in result.tasks_output:
                    if hasattr(task_output, 'raw'):
                        tool_output = str(task_output.raw)
                        if "[IMAGE:" in tool_output:
                            logger.info("Found [IMAGE:...] references in task output, appending to summary")
                            # Extract image references and append them
                            import re
                            image_refs = re.findall(r'\[IMAGE:([^\]]+)\]', tool_output)
                            if image_refs:
                                cleaned_content += "\n\n**Related Images:**\n" + "\n".join([f"[IMAGE:{ref}]" for ref in image_refs])
                                logger.info(f"Added {len(image_refs)} image reference(s) to summary")

        base_url = "/api/images/"
        # Extract context text for image explanations (first 1000 chars of summary)
        context_for_explanations = cleaned_content[:1000] if len(cleaned_content) > 1000 else cleaned_content
        # Check if image explanations are enabled (can be disabled via env var if network issues)
        generate_explanations = settings.ENABLE_IMAGE_EXPLANATIONS
        logger.info(f"Image explanations setting: ENABLE_IMAGE_EXPLANATIONS = {generate_explanations}")
        if not generate_explanations:
            logger.info("⚠ Image explanations DISABLED via ENABLE_IMAGE_EXPLANATIONS setting")
        else:
            logger.info("✓ Image explanations ENABLED - will generate explanations for images")
        final_content, image_paths = extract_and_replace_images(
            cleaned_content, 
            base_url=base_url,
            topic=topic,
            generate_explanations=generate_explanations,
            context_text=context_for_explanations
        )

        # ✅ Generate audio from cleaned content (optional; skipped if Piper not configured)
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(final_content)  # outputs/audio/xxx.wav or None
            if audio_path:
                audio_url = f"/audio/{Path(audio_path).name}"
                logger.info(f"✅ Audio generated: {audio_url}")
            else:
                logger.info("TTS skipped (Piper not configured)")
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)

        # Store base summary in MongoDB (only if doesn't exist, unless force=True)
        summary_id = service.store_base_summary(
            topic=topic,
            summary_text=final_content,
            images=image_paths,
            audio_url=audio_url,
            force=force,
            user_email=user.email,
        )
        
        # summary_id should always be returned (either existing ID or new/updated ID)
        if not summary_id:
            logger.error(f"Failed to store base summary for topic '{topic}'")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store summary"
            )

        logger.info(f"Successfully created and stored summary (length: {len(final_content)})")
        logger.info(f"Found {len(image_paths)} image(s) in summary")
        
        # Verify HTML is in the final content before storing
        figure_count = final_content.count('<figure>')
        figcaption_count = final_content.count('<figcaption>')
        logger.info(f"📊 Final content verification: {figure_count} <figure> tags, {figcaption_count} <figcaption> tags")
        if figure_count == 0 and len(image_paths) > 0:
            logger.warning(f"⚠ WARNING: {len(image_paths)} images found but NO figure tags in final content!")
            logger.warning(f"Content preview (first 500 chars): {final_content[:500]}")
        
        logger.info("=== Summarization completed ===")

        # Persist audio blob + duration metadata (optional)
        from bson.objectid import ObjectId
        audio_duration_seconds = None
        if audio_path and audio_url and summary_id:
            attach = service.attach_audio_to_summary(
                summary_id=summary_id,
                topic=topic,
                summary_type="base",
                audio_path=audio_path,
                user_email=user.email,
            )
            audio_duration_seconds = attach.get("audio_duration_seconds")
            # Prefer GridFS URL so audio works even if static file is missing
            if attach.get("audio_file_id"):
                audio_url = f"/protected/summaries/{summary_id}/audio"
                service.summaries_collection.update_one(
                    {"_id": ObjectId(summary_id)},
                    {"$set": {"audio_url": audio_url}},
                )

        # Get the stored summary to get created_at (+ possibly duration)
        stored_summary = service.summaries_collection.find_one({"_id": ObjectId(summary_id)})
        effective_audio_url = _effective_audio_url(stored_summary) if stored_summary else audio_url

        return {
            "summary": final_content,
            "images": image_paths,
            "topic": topic,
            "audio_url": effective_audio_url,
            "summary_id": summary_id,
            "summary_type": "base",
            "created_at": stored_summary.get("created_at").isoformat() if stored_summary and stored_summary.get("created_at") else None,
            "audio_duration_seconds": stored_summary.get("audio_duration_seconds") if stored_summary else audio_duration_seconds,
            "from_cache": False
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "space quota" in err_msg.lower() or "over your space quota" in err_msg.lower():
            raise HTTPException(
                status_code=507,  # Insufficient Storage
                detail="Database storage quota exceeded. Please free space in MongoDB Atlas or upgrade your plan, then try again."
            )
        logger.error(f"Error creating summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create summary: {e}"
        )


class CheckSummaryAccuracyRequest(BaseModel):
    topic: str
    summary_content: str


class CheckGuidanceAccuracyRequest(BaseModel):
    guidance_content: str
    assignment_topic: Optional[str] = None


class FlashcardRequest(BaseModel):
    topic: str
    force: bool = False  # If True, regenerate even if exists in DB (same as SummarizeRequest)


@router.post("/check-summary-accuracy")
async def check_summary_accuracy(
    request: CheckSummaryAccuracyRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Check the accuracy of a summary using ROUGE metrics.
    
    Returns:
        JSON response with ROUGE scores and accuracy assessment
    """
    logger.info(f"=== Checking summary accuracy for topic: {request.topic} ===")
    
    try:
        rag_chain = _get_rag_chain()
        
        if rag_chain is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RAG system is not available. The vectorstore needs to be built first."
            )
        
        # Query for relevant context
        summary_query = f"Provide detailed information about {request.topic} from lecture materials"
        result = rag_chain.invoke({"question": summary_query})
        
        # Extract context and verify accuracy
        context_text = _extract_context_text(result)
        
        if not context_text:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No relevant context found in lecture materials for this topic."
            )
        
        accuracy_result = _verify_summary_accuracy(
            summary=request.summary_content,
            context_text=context_text,
            topic=request.topic
        )
        
        logger.info(f"Accuracy check completed. Overall F-measure: {accuracy_result.get('overall', {}).get('avg_fmeasure_pct', 0):.2f}%")
        
        return accuracy_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking summary accuracy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check summary accuracy: {e}"
        )


@router.post("/check-guidance-accuracy")
async def check_guidance_accuracy(
    request: CheckGuidanceAccuracyRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Check the accuracy of CA guidance using ROUGE metrics.
    
    Returns:
        JSON response with ROUGE scores and accuracy assessment
    """
    logger.info("=== Checking guidance accuracy ===")
    
    try:
        accuracy_result = verify_guidance_accuracy(
            guidance_text=request.guidance_content,
            assignment_topic=request.assignment_topic or ""
        )
        
        logger.info(f"Accuracy check completed. Overall F-measure: {accuracy_result.get('overall', {}).get('avg_fmeasure_pct', 0):.2f}%")
        
        return accuracy_result
        
    except Exception as e:
        logger.error(f"Error checking guidance accuracy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check guidance accuracy: {e}"
        )


@router.post("/generate-flashcards")
async def generate_flashcards(
    request: FlashcardRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Create or retrieve Bloom's Taxonomy-based flashcards for a given topic.

    Default (force=False): Returns this user's previously saved flashcards for the topic
    from the database—their most recently stored set for that topic. User-specific; always
    the latest version available for that topic.

    Force regenerate (force=True): Generates new flashcards for the topic, then the frontend
    saves them to the database under this user's profile for future access. New sets are
    stored and can be accessed whenever needed.

    Storage and viewability: All sets are stored per user (user_email). Whether pulled
    from DB or newly generated, the flashcards returned are recent and specific to the user.
    """
    topic = request.topic.strip()
    force = request.force
    logger.info(f"=== Starting flashcard get/generate for topic: {topic} (force={force}) ===")

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty."
        )

    try:
        from app.core.config import settings as _settings
        # Check for existing flashcard set if not forcing regeneration (same pattern as summarize_topic)
        if not force:
            from pymongo import MongoClient
            import certifi

            client = MongoClient(_settings.MONGO_URI, tlsCAFile=certifi.where())
            db = client.ca_guidance
            flashcard_sets = db.flashcard_sets
            # Most recent saved set for this user and topic (case-insensitive topic match)
            topic_regex = re.compile(f"^{re.escape(topic)}$", re.IGNORECASE)
            flashcard_set = flashcard_sets.find_one(
                {"topic": topic_regex, "user_email": user.email},
                sort=[("created_at", -1)]
            )
            if flashcard_set:
                logger.info(f"Found saved flashcard set for topic '{topic}' (user-specific)")
                return {
                    "topic": flashcard_set["topic"],
                    "flashcards": flashcard_set["flashcards"],
                    "flashcard_set_id": str(flashcard_set["_id"]),
                    "from_saved": True,
                    "from_cache": True,  # Same key as summarization when returning stored
                }
            logger.info(f"No saved set for topic '{topic}', will generate")

        # Generate new flashcards
        from langchain_openai import ChatOpenAI
        from app.ca_guidance.agents.flashcard_agent import FlashcardAgent
        
        # Initialize LLM for flashcard generation
        # Use GPT model explicitly for flashcard generation
        model_name = "gpt-4o-mini"  # Use GPT model for flashcard generation
        llm = ChatOpenAI(
            model=model_name,
            api_key=_settings.OPENAI_API_KEY,
            temperature=0.3,  # Lower temperature for more consistent flashcard generation
        )
        
        # Create flashcard agent
        agent = FlashcardAgent(llm=llm)
        
        logger.info("Step 1: Generating flashcards using FlashcardAgent")
        result = agent.generate_flashcards(topic)
        
        logger.info(f"Successfully generated flashcards for topic: {topic}")
        logger.info("=== Flashcard generation completed ===")
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating flashcards: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate flashcards: {str(e)}"
        )


# ============ Flashcard Feedback Endpoints ============

@router.post("/flashcards/save")
async def save_flashcard_set(
    request: SaveFlashcardSetRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Save a generated flashcard set to the database under this user's profile.
    Stored sets are available for future access (default flow will pull them by topic).
    """
    logger.info(f"=== Saving flashcard set for topic: {request.topic} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        import uuid
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        # Add unique IDs to each flashcard if they don't have one
        flashcards_with_ids = {}
        for level, cards in request.flashcards.items():
            flashcards_with_ids[level] = []
            for card in cards:
                flashcards_with_ids[level].append({
                    "id": card.get("id") or str(uuid.uuid4()),
                    "question": card["question"],
                    "answer": card["answer"]
                })
        
        doc = {
            "topic": request.topic,
            "user_email": user.email,
            "flashcards": flashcards_with_ids,
            "version": 1,
            "created_at": datetime.utcnow(),
            "updated_at": None
        }
        
        result = flashcard_sets.insert_one(doc)
        logger.info(f"Flashcard set saved with ID: {result.inserted_id}")
        
        return {
            "flashcard_set_id": str(result.inserted_id),
            "topic": request.topic,
            "flashcards": flashcards_with_ids,
            "version": 1,
            "message": "Flashcard set saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving flashcard set: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save flashcard set: {str(e)}"
        )


@router.post("/flashcards/feedback")
async def submit_flashcard_feedback(
    request: FlashcardFeedbackRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Submit feedback for a specific flashcard."""
    logger.info(f"=== Submitting feedback for flashcard {request.flashcard_id} ===")
    
    try:
        from datetime import datetime
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_feedback = db.flashcard_feedback
        
        doc = {
            "flashcard_set_id": request.flashcard_set_id,
            "flashcard_id": request.flashcard_id,
            "bloom_level": request.bloom_level,
            "user_email": user.email,
            "rating": request.rating,
            "feedback_type": request.feedback_type,
            "comment": request.comment,
            "session_id": request.session_id,
            "created_at": datetime.utcnow(),
            "processed": False
        }
        
        result = flashcard_feedback.insert_one(doc)
        logger.info(f"Flashcard feedback stored (id: {result.inserted_id})")
        
        return {
            "feedback_id": str(result.inserted_id),
            "flashcard_set_id": request.flashcard_set_id,
            "flashcard_id": request.flashcard_id,
            "message": "Feedback submitted successfully"
        }
        
    except Exception as e:
        logger.error(f"Error storing flashcard feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {str(e)}"
        )


@router.post("/flashcards/improve")
async def improve_flashcard(
    request: FlashcardUpdateRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Improve a flashcard based on submitted feedback."""
    logger.info(f"=== Improving flashcard {request.flashcard_id} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from langchain_openai import ChatOpenAI
        from app.core.config import settings
        from app.ca_guidance.agents.flashcard_improvement_agent import FlashcardImprovementAgent
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        flashcard_feedback = db.flashcard_feedback
        
        feedback_doc = flashcard_feedback.find_one({"_id": ObjectId(request.feedback_id)})
        if not feedback_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
        
        flashcard_set = flashcard_sets.find_one({"_id": ObjectId(request.flashcard_set_id)})
        if not flashcard_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")
        
        bloom_level = request.bloom_level
        flashcard = None
        flashcard_index = -1
        
        if bloom_level in flashcard_set["flashcards"]:
            for i, card in enumerate(flashcard_set["flashcards"][bloom_level]):
                if card["id"] == request.flashcard_id:
                    flashcard = card
                    flashcard_index = i
                    break
        
        if not flashcard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")
        
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.3)
        agent = FlashcardImprovementAgent(llm=llm)
        
        improved = agent.improve_flashcard(
            topic=flashcard_set["topic"],
            question=flashcard["question"],
            answer=flashcard["answer"],
            bloom_level=bloom_level,
            feedback_type=feedback_doc.get("feedback_type"),
            comment=feedback_doc.get("comment")
        )
        
        new_version = flashcard_set.get("version", 1) + 1
        
        flashcard_sets.update_one(
            {"_id": ObjectId(request.flashcard_set_id)},
            {
                "$set": {
                    f"flashcards.{bloom_level}.{flashcard_index}.question": improved["question"],
                    f"flashcards.{bloom_level}.{flashcard_index}.answer": improved["answer"],
                    "version": new_version,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        flashcard_feedback.update_one(
            {"_id": ObjectId(request.feedback_id)},
            {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
        )
        
        logger.info(f"Flashcard improved successfully. New version: {new_version}")
        
        return {
            "flashcard_id": request.flashcard_id,
            "bloom_level": bloom_level,
            "original_question": flashcard["question"],
            "original_answer": flashcard["answer"],
            "updated_question": improved["question"],
            "updated_answer": improved["answer"],
            "improvement_notes": improved["improvement_notes"],
            "version": new_version,
            "message": "Flashcard improved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error improving flashcard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to improve flashcard: {str(e)}"
        )


@router.get("/flashcards/recent")
async def get_recent_flashcards(
    user: UserInfo = Depends(get_current_user)
):
    """Get the most recently created flashcard set for the current user."""
    logger.info("=== Getting recent flashcard set for user ===")
    try:
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi

        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets

        flashcard_set = flashcard_sets.find_one(
            {"user_email": user.email},
            sort=[("created_at", -1)]
        )
        if not flashcard_set:
            return {"found": False, "message": "No flashcards found for this user"}

        return {
            "found": True,
            "_id": str(flashcard_set["_id"]),
            "topic": flashcard_set["topic"],
            "flashcards": flashcard_set["flashcards"],
            "version": flashcard_set.get("version", 1),
            "created_at": flashcard_set["created_at"].isoformat() if flashcard_set.get("created_at") else None,
            "updated_at": flashcard_set["updated_at"].isoformat() if flashcard_set.get("updated_at") else None,
        }
    except Exception as e:
        logger.error(f"Error getting recent flashcards: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recent flashcards: {str(e)}"
        )


@router.get("/flashcards/topic/{topic}")
async def get_flashcards_by_topic(
    topic: str,
    user: UserInfo = Depends(get_current_user)
):
    """Get the most recently saved flashcard set for this user and topic."""
    logger.info(f"=== Getting flashcards for topic: {topic} ===")
    
    try:
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        flashcard_set = flashcard_sets.find_one(
            {"topic": topic, "user_email": user.email},
            sort=[("created_at", -1)]
        )
        
        if not flashcard_set:
            return {"found": False, "message": "No flashcards found for this topic"}
        
        return {
            "found": True,
            "_id": str(flashcard_set["_id"]),
            "topic": flashcard_set["topic"],
            "flashcards": flashcard_set["flashcards"],
            "version": flashcard_set.get("version", 1),
            "created_at": flashcard_set["created_at"].isoformat() if flashcard_set.get("created_at") else None,
            "updated_at": flashcard_set["updated_at"].isoformat() if flashcard_set.get("updated_at") else None
        }
        
    except Exception as e:
        logger.error(f"Error getting flashcards by topic: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get flashcards: {str(e)}"
        )


@router.get("/flashcards/{flashcard_set_id}")
async def get_flashcard_set(
    flashcard_set_id: str,
    user: UserInfo = Depends(get_current_user)
):
    """Get a flashcard set by ID."""
    logger.info(f"=== Getting flashcard set {flashcard_set_id} ===")
    
    try:
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        flashcard_set = flashcard_sets.find_one({"_id": ObjectId(flashcard_set_id)})
        if not flashcard_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")
        
        return {
            "_id": str(flashcard_set["_id"]),
            "topic": flashcard_set["topic"],
            "flashcards": flashcard_set["flashcards"],
            "version": flashcard_set.get("version", 1),
            "created_at": flashcard_set["created_at"].isoformat() if flashcard_set.get("created_at") else None,
            "updated_at": flashcard_set["updated_at"].isoformat() if flashcard_set.get("updated_at") else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flashcard set: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get flashcard set: {str(e)}"
        )


# ============ Summary Feedback Endpoints ============

@router.post("/summaries/feedback")
async def submit_summary_feedback(
    request: SummaryFeedbackRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Submit feedback for a summary.
    
    Returns:
        JSON response with feedback_id
    """
    logger.info(f"=== Submitting feedback for summary {request.summary_id} ===")
    
    try:
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        
        feedback_id = service.store_feedback(
            topic=request.topic,
            summary_id=request.summary_id,
            rating=request.rating,
            confused_concept=request.confused_concept,
            comment=request.comment,
            feedback_type=request.feedback_type,
            user_email=user.email,
            session_id=request.session_id,
        )
        
        logger.info(f"Feedback stored successfully (id: {feedback_id})")
        
        return {
            "feedback_id": feedback_id,
            "message": "Feedback submitted successfully"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error storing feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {e}"
        )


@router.post("/summaries/reinforce")
async def reinforce_summary(
    request: ReinforceSummaryRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Generate a reinforced summary based on feedback.
    
    Returns:
        JSON response with reinforced summary, images, audio_url, and summary_id
    """
    logger.info(f"=== Generating reinforced summary for topic: {request.topic} (force={request.force}) ===")
    
    try:
        from bson.objectid import ObjectId
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        
        # Check if reinforced summary exists and force=False
        if not request.force:
            existing_reinforced = service.get_latest_summary(request.topic, prefer_reinforced=True, user_email=user.email)
            if existing_reinforced and existing_reinforced.get("summary_type") == "reinforced":
                logger.info(f"Found existing reinforced summary for topic '{request.topic}'")
                return {
                    "summary": existing_reinforced["summary_text"],
                    "images": existing_reinforced.get("images", []),
                    "topic": request.topic,
                    "audio_url": _effective_audio_url(existing_reinforced),
                    "summary_id": existing_reinforced["_id"],
                    "summary_type": "reinforced",
                    "created_at": existing_reinforced.get("created_at").isoformat() if existing_reinforced.get("created_at") else None,
                    "audio_duration_seconds": existing_reinforced.get("audio_duration_seconds"),
                    "from_cache": True
                }
        
        # Get the base summary
        try:
            summary_obj_id = ObjectId(request.summary_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid summary_id format: {request.summary_id}"
            )
        
        base_summary_doc = service.summaries_collection.find_one({"_id": summary_obj_id})
        
        if not base_summary_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary with id {request.summary_id} not found"
            )
        
        base_summary_text = base_summary_doc["summary_text"]
        
        # Get feedback - prioritize feedback_id if provided, otherwise get latest for this summary
        feedback = {}
        feedback_id_to_store = None
        
        if request.feedback_id:
            try:
                feedback_obj_id = ObjectId(request.feedback_id)
                feedback_doc = service.feedback_collection.find_one({"_id": feedback_obj_id})
                if feedback_doc:
                    feedback = {
                        "rating": feedback_doc.get("rating", "not_helpful"),
                        "confused_concept": feedback_doc.get("confused_concept"),
                        "comment": feedback_doc.get("comment"),
                        "feedback_type": feedback_doc.get("feedback_type"),
                    }
                    feedback_id_to_store = str(feedback_obj_id)
                    logger.info(f"Using specific feedback_id: {feedback_id_to_store}")
            except Exception as e:
                logger.warning(f"Invalid feedback_id format: {request.feedback_id}, error: {e}")
        
        # If no feedback_id provided or invalid, get latest feedback for this summary
        if not feedback:
            latest_feedback = service.get_latest_feedback_for_summary(
                request.summary_id, user_email=user.email, session_id=request.session_id
            )
            if latest_feedback:
                feedback = {
                    "rating": latest_feedback.get("rating", "not_helpful"),
                    "confused_concept": latest_feedback.get("confused_concept"),
                    "comment": latest_feedback.get("comment"),
                    "feedback_type": latest_feedback.get("feedback_type"),
                }
                feedback_id_to_store = latest_feedback.get("_id")
                logger.info(f"Using latest feedback for summary: {feedback_id_to_store}")
        
        # Default feedback if none found
        if not feedback:
            feedback = {"rating": "not_helpful"}  # Default
            logger.warning("No feedback found, using default 'not_helpful'")
        
        # Generate reinforced summary
        logger.info("Generating reinforced summary using LLM...")
        reinforced_text = service.generate_reinforced_summary(
            topic=request.topic,
            base_summary_text=base_summary_text,
            feedback=feedback
        )
        
        # Generate audio for reinforced summary (optional; skipped if Piper not configured)
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(reinforced_text)
            if audio_path:
                audio_url = f"/audio/{Path(audio_path).name}"
                logger.info(f"✅ Audio generated for reinforced summary: {audio_url}")
            else:
                logger.info("TTS skipped (Piper not configured)")
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)
        
        # Extract images from base summary (reuse them)
        images = base_summary_doc.get("images", [])
        
        # Store reinforced summary (use feedback_id_to_store if we found one)
        reinforced_summary_id = service.store_reinforced_summary(
            topic=request.topic,
            summary_text=reinforced_text,
            base_summary_id=request.summary_id,
            feedback_id=feedback_id_to_store or request.feedback_id,
            images=images,
            audio_url=audio_url,
            user_email=user.email,
            session_id=request.session_id,
        )

        # Persist audio blob + duration metadata (optional)
        audio_duration_seconds = None
        if audio_path and audio_url and reinforced_summary_id:
            attach = service.attach_audio_to_summary(
                summary_id=reinforced_summary_id,
                topic=request.topic,
                summary_type="reinforced",
                audio_path=audio_path,
                user_email=user.email,
                session_id=request.session_id,
            )
            audio_duration_seconds = attach.get("audio_duration_seconds")
            if attach.get("audio_file_id"):
                audio_url = f"/protected/summaries/{reinforced_summary_id}/audio"
                service.summaries_collection.update_one(
                    {"_id": ObjectId(reinforced_summary_id)},
                    {"$set": {"audio_url": audio_url}},
                )
        
        logger.info(f"Reinforced summary generated and stored (id: {reinforced_summary_id})")
        
        # Get the stored reinforced summary to get created_at
        stored_reinforced = service.summaries_collection.find_one({"_id": ObjectId(reinforced_summary_id)})
        effective_audio_url = _effective_audio_url(stored_reinforced) if stored_reinforced else audio_url
        
        return {
            "summary": reinforced_text,
            "images": images,
            "topic": request.topic,
            "audio_url": effective_audio_url,
            "summary_id": reinforced_summary_id,
            "summary_type": "reinforced",
            "base_summary_id": request.summary_id,
            "feedback_id": request.feedback_id,
            "created_at": stored_reinforced.get("created_at").isoformat() if stored_reinforced and stored_reinforced.get("created_at") else None,
            "audio_duration_seconds": stored_reinforced.get("audio_duration_seconds") if stored_reinforced else audio_duration_seconds,
            "from_cache": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reinforced summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reinforced summary: {e}"
        )


@router.get("/summaries/{summary_id}/audio")
async def get_summary_audio(
    summary_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """
    Stream summary audio from GridFS (WAV). Use this URL when summary has audio stored.
    """
    from bson.objectid import ObjectId
    from app.services.summary_reinforcement_service import SummaryReinforcementService

    try:
        oid = ObjectId(summary_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid summary_id")

    service = SummaryReinforcementService()
    doc = service.summaries_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")

    # Optional: restrict to same user (or allow if no user_email on doc)
    if doc.get("user_email") and doc.get("user_email") != user.email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")

    audio_file_id = doc.get("audio_file_id")
    if not audio_file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audio available for this summary")

    try:
        grid_out = service.audio_fs.get(ObjectId(audio_file_id) if isinstance(audio_file_id, str) else audio_file_id)
    except Exception as e:
        logger.warning(f"GridFS get failed for summary {summary_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")

    file_length = getattr(grid_out, "length", None)
    if file_length is None and hasattr(grid_out, "_file"):
        file_length = grid_out._file.get("length")

    def stream():
        chunk_size = 64 * 1024  # 64KB so first chunk arrives quickly for playback start
        try:
            while True:
                chunk = grid_out.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            grid_out.close()

    headers = {
        "Content-Disposition": "inline; filename=summary_audio.wav",
        "Cache-Control": "private, max-age=300",
    }
    if file_length is not None:
        headers["Content-Length"] = str(file_length)
        headers["Accept-Ranges"] = "bytes"

    return StreamingResponse(
        stream(),
        media_type="audio/wav",
        headers=headers,
    )


@router.get("/summaries/topic/{topic}")
async def get_summaries_for_topic(
    topic: str,
    user: UserInfo = Depends(get_current_user)
):
    """
    Get all summaries (base and reinforced) for a topic.
    
    Returns:
        JSON response with both base and reinforced summaries
    """
    logger.info(f"=== Getting all summaries for topic: {topic} ===")
    
    try:
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        summaries = service.get_all_summaries_for_topic(topic, user_email=user.email)
        
        # Ensure audio_url is set from GridFS when we have audio_file_id
        base = summaries.get("base")
        reinforced = summaries.get("reinforced")
        if base:
            base["audio_url"] = _effective_audio_url(base)
        if reinforced:
            reinforced["audio_url"] = _effective_audio_url(reinforced)

        result = {
            "topic": topic,
            "base": base,
            "reinforced": reinforced
        }
        
        logger.info(f"Retrieved summaries for topic '{topic}'")
        return result
        
    except Exception as e:
        logger.error(f"Error getting summaries: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get summaries: {e}"
        )


# ============ Guidance Feedback and Reinforcement (same style as summarization) ============

@router.post("/guidance/feedback")
async def submit_guidance_feedback(
    request: GuidanceFeedbackRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Submit feedback for CA guidance. Required before reinforcement."""
    logger.info(f"=== Submitting feedback for guidance {request.guidance_id} ===")
    try:
        from app.services.guidance_reinforcement_service import GuidanceReinforcementService
        service = GuidanceReinforcementService()
        base = service.get_guidance(request.guidance_id, user_email=user.email)
        if not base or base.get("guidance_type") != "base":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base guidance not found or invalid.",
            )
        feedback_id = service.store_feedback(
            guidance_id=request.guidance_id,
            rating=request.rating,
            confused_concept=request.confused_concept,
            comment=request.comment,
            feedback_type=request.feedback_type,
            deadline_text=request.deadline_text,
            user_email=user.email,
            session_id=request.session_id,
        )
        return {"feedback_id": feedback_id, "message": "Feedback submitted successfully"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error storing guidance feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit guidance feedback: {e}",
        )


@router.post("/guidance/reinforce")
async def reinforce_guidance(
    request: ReinforceGuidanceRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Generate reinforced CA guidance from the latest feedback (same flow as summarization)."""
    logger.info(f"=== Generating reinforced guidance for {request.guidance_id} (force={request.force}) ===")
    try:
        from bson.objectid import ObjectId
        from app.services.guidance_reinforcement_service import GuidanceReinforcementService
        service = GuidanceReinforcementService()
        base = service.get_guidance(request.guidance_id, user_email=user.email)
        if not base or base.get("guidance_type") != "base":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base guidance not found.",
            )
        if not request.force:
            reinforced = service.get_reinforced_guidance(request.guidance_id, user_email=user.email)
            if reinforced:
                return {
                    "report": reinforced["report_text"],
                    "images": reinforced.get("images", []),
                    "guidance_id": request.guidance_id,
                    "reinforced_guidance_id": reinforced["_id"],
                    "guidance_type": "reinforced",
                    "from_cache": True,
                    "created_at": reinforced.get("created_at").isoformat() if reinforced.get("created_at") else None,
                }
        # Ensure we always work with the most recent version: reinforced (if any) or base.
        # All feedback (deadline, links, simplify, clarifications) is applied to this version
        # so the final document incorporates every change.
        latest_source = service.get_latest_guidance_for_reinforcement(request.guidance_id, user_email=user.email)
        if not latest_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not resolve latest guidance to reinforce.",
            )
        # Use the feedback that was just submitted (request.feedback_id from frontend) so the deadline is the one the user entered
        feedback = None
        feedback_id_to_store = request.feedback_id
        if request.feedback_id:
            try:
                fd = service.feedback_collection.find_one({"_id": ObjectId(request.feedback_id)})
                if fd:
                    feedback = {
                        "rating": fd.get("rating", "not_helpful"),
                        "confused_concept": fd.get("confused_concept"),
                        "comment": fd.get("comment"),
                        "feedback_type": fd.get("feedback_type"),
                        "deadline_text": fd.get("deadline_text"),
                    }
                    feedback_id_to_store = str(fd["_id"])
                    if fd.get("deadline_text"):
                        logger.info(f"Using deadline from submitted feedback: {fd.get('deadline_text')!r}")
            except Exception as e:
                logger.warning(f"Could not load feedback by id {request.feedback_id}: {e}")
        if not feedback:
            feedback_doc = service.get_latest_feedback_for_guidance(
                request.guidance_id, user_email=user.email, session_id=request.session_id
            )
            if feedback_doc:
                feedback = {
                    "rating": feedback_doc.get("rating", "not_helpful"),
                    "confused_concept": feedback_doc.get("confused_concept"),
                    "comment": feedback_doc.get("comment"),
                    "feedback_type": feedback_doc.get("feedback_type"),
                    "deadline_text": feedback_doc.get("deadline_text"),
                }
                feedback_id_to_store = feedback_doc.get("_id")
        if not feedback:
            feedback = {"rating": "not_helpful"}
        # For new_deadline_event: use ONLY the user-provided deadline from feedback. Do not use any deadline from the document.
        calendar_event_message = None
        user_provided_deadline = (feedback.get("deadline_text") or "").strip()
        access_token = getattr(user, "access_token", None) or (user.access_token if hasattr(user, "access_token") else None)
        if feedback.get("feedback_type") == "new_deadline_event" and user_provided_deadline:
            # Create calendar event with the user's new deadline only (never document-extracted deadline).
            if access_token:
                try:
                    from app.ca_guidance.tools.calendar_tool import create_calendar_event_with_token
                    calendar_event_message = create_calendar_event_with_token(
                        access_token=access_token,
                        title="CA Assignment: New deadline",
                        start_date=user_provided_deadline,
                        duration_hours=1,
                    )
                    logger.info(f"Calendar event (user deadline only): {calendar_event_message}")
                except Exception as cal_err:
                    logger.warning(f"Could not create calendar event: {cal_err}")
                    calendar_event_message = f"Calendar event could not be created: {cal_err}"
            else:
                calendar_event_message = (
                    "Calendar event was not created. Please sign in with Google to add the deadline to your calendar."
                )
                logger.info(f"No access token; calendar not created for deadline: {user_provided_deadline!r}")
        # Apply feedback to the latest version (never to a stale base)
        reinforced_text = service.generate_reinforced_guidance(
            base_report_text=latest_source["report_text"],
            feedback=feedback,
        )
        # 2) If user added a new deadline: remove any existing deadline/calendar section from the LLM output
        #    (it may contain an old date from the document), then append a single section with the user's date.
        if feedback.get("feedback_type") == "new_deadline_event" and user_provided_deadline:
            # Remove any ### heading that mentions Deadline or Calendar and its content up to the next ### or end
            def remove_deadline_sections(text: str) -> str:
                lines = text.split("\n")
                out = []
                skip_until_next_heading = False
                for line in lines:
                    if re.match(r"^#{2,6}\s+.*(?:deadline|calendar\s*confirmation|important\s*dates)", line, re.IGNORECASE):
                        skip_until_next_heading = True
                        continue
                    if skip_until_next_heading and re.match(r"^#{2,6}\s+", line):
                        skip_until_next_heading = False
                    if not skip_until_next_heading:
                        out.append(line)
                return "\n".join(out).rstrip()

            reinforced_text = remove_deadline_sections(reinforced_text)
            deadline_section = (
                "\n\n### Deadline / Calendar Confirmation\n\n"
                f"Your new deadline is **{user_provided_deadline}**. "
            )
            if calendar_event_message and "Successfully scheduled" in (calendar_event_message or ""):
                deadline_section += "The event has been added to your Google Calendar."
            elif calendar_event_message:
                deadline_section += "The calendar event could not be created automatically; please add this date to your calendar manually if needed."
            else:
                deadline_section += "Sign in with Google to add this deadline to your calendar."
            reinforced_text = reinforced_text.rstrip() + deadline_section
            logger.info(f"Deadline section set to user-provided date: {user_provided_deadline!r}")
        images = latest_source.get("images", [])  # preserve images from latest version
        reinforced_id = service.store_reinforced_guidance(
            base_guidance_id=request.guidance_id,
            report_text=reinforced_text,
            feedback_id=feedback_id_to_store,
            images=images,
            user_email=user.email,
            session_id=request.session_id,
        )
        stored = service.guidances_collection.find_one({"_id": ObjectId(reinforced_id)})
        response_data = {
            "report": reinforced_text,
            "images": images,
            "guidance_id": request.guidance_id,
            "reinforced_guidance_id": reinforced_id,
            "guidance_type": "reinforced",
            "from_cache": False,
            "created_at": stored.get("created_at").isoformat() if stored and stored.get("created_at") else None,
            "message": "Guidance updated with your feedback. You are viewing the latest version with all changes applied.",
        }
        # Always confirm calendar outcome in the response when user set a new deadline
        if feedback.get("feedback_type") == "new_deadline_event" and user_provided_deadline:
            response_data["calendar_event_message"] = calendar_event_message or (
                "Deadline was recorded; calendar event could not be created."
            )
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reinforced guidance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reinforced guidance: {e}",
        )
