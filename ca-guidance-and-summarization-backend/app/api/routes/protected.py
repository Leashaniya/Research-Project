import fitz  # PyMuPDF
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from app.core.dependencies import get_current_user
from app.models.schemas import UserInfo, SummarizeRequest
from app.ca_guidance.crew import create_guidance_crew, create_summarization_crew
from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR
from app.ca_guidance.tools.tts_tool import text_to_speech_wav  # ✅ AUDIO

logger = logging.getLogger(__name__)

def extract_and_replace_images(content: str, base_url: str = "/api/images/") -> tuple[str, list[str]]:
    """
    Extract image references from markdown and replace with proper image tags.
    Returns (cleaned_content, list_of_image_paths)
    """
    if not content:
        return content, []

    image_paths = []
    image_pattern = r'\[IMAGE:([^\]]+)\]'

    available_images = {}
    if IMAGE_OUTPUT_DIR.exists():
        for img_file in IMAGE_OUTPUT_DIR.glob("*"):
            if img_file.is_file() and img_file.suffix.lower() in ['.jpeg', '.jpg', '.png', '.gif']:
                available_images[img_file.name] = img_file.name
                available_images[img_file.name.lower()] = img_file.name

    def replace_image(match):
        img_name = match.group(1).strip()
        import urllib.parse

        if img_name in available_images:
            actual_name = available_images[img_name]
            image_paths.append(actual_name)
            encoded_name = urllib.parse.quote(actual_name)
            return f'![{actual_name}]({base_url}{encoded_name})'

        img_name_lower = img_name.lower()
        if img_name_lower in available_images:
            actual_name = available_images[img_name_lower]
            image_paths.append(actual_name)
            encoded_name = urllib.parse.quote(actual_name)
            return f'![{actual_name}]({base_url}{encoded_name})'

        for available_name in available_images.values():
            if available_name.lower().startswith(img_name_lower) or img_name_lower in available_name.lower():
                image_paths.append(available_name)
                encoded_name = urllib.parse.quote(available_name)
                return f'![{available_name}]({base_url}{encoded_name})'

        return match.group(0)

    cleaned_content = re.sub(image_pattern, replace_image, content)
    return cleaned_content, list(set(image_paths))


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
        final_content, image_paths = extract_and_replace_images(cleaned_content, base_url)

        logger.info(f"Successfully extracted markdown (length: {len(final_content)})")
        logger.info(f"Found {len(image_paths)} image(s) in response")
        logger.info("=== Guidance process completed ===")

        return {
            "report": final_content,
            "images": image_paths
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

    Returns:
        JSON response with summary, related images, and audio_url
    """
    topic = request.topic.strip()
    logger.info(f"=== Starting summarization for topic: {topic} ===")

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty."
        )

    logger.info("Step 1: Creating and running summarization crew")
    try:
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

        base_url = "/api/images/"
        final_content, image_paths = extract_and_replace_images(cleaned_content, base_url)

        # ✅ Generate audio from cleaned content
        audio_url = None
        try:
            audio_path = text_to_speech_wav(final_content)  # outputs/audio/xxx.wav
            audio_url = f"/audio/{Path(audio_path).name}"
            logger.info(f"✅ Audio generated: {audio_url}")
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)

        logger.info(f"Successfully created summary (length: {len(final_content)})")
        logger.info(f"Found {len(image_paths)} image(s) in summary")
        logger.info("=== Summarization completed ===")

        return {
            "summary": final_content,
            "images": image_paths,
            "topic": topic,
            "audio_url": audio_url
        }

    except Exception as e:
        logger.error(f"Error creating summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create summary: {e}"
        )
