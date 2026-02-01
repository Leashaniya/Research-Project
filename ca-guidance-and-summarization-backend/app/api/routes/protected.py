import fitz  # PyMuPDF
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
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
    FlashcardFeedbackRequest,
    FlashcardUpdateRequest,
    SaveFlashcardSetRequest,
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
                return {
                    "summary": existing_summary["summary_text"],
                    "images": existing_summary.get("images", []),
                    "topic": topic,
                    "audio_url": existing_summary.get("audio_url"),
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

        base_url = "/api/images/"
        final_content, image_paths = extract_and_replace_images(cleaned_content, base_url)

        # ✅ Generate audio from cleaned content
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(final_content)  # outputs/audio/xxx.wav
            audio_url = f"/audio/{Path(audio_path).name}"
            logger.info(f"✅ Audio generated: {audio_url}")
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
        logger.info("=== Summarization completed ===")

        # Persist audio blob + duration metadata (optional)
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

        # Get the stored summary to get created_at (+ possibly duration)
        from bson.objectid import ObjectId
        stored_summary = service.summaries_collection.find_one({"_id": ObjectId(summary_id)})
        
        return {
            "summary": final_content,
            "images": image_paths,
            "topic": topic,
            "audio_url": audio_url,
            "summary_id": summary_id,
            "summary_type": "base",
            "created_at": stored_summary.get("created_at").isoformat() if stored_summary and stored_summary.get("created_at") else None,
            "audio_duration_seconds": stored_summary.get("audio_duration_seconds") if stored_summary else audio_duration_seconds,
            "from_cache": False
        }

    except Exception as e:
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
    Generate Bloom's Taxonomy-based flashcards for a given topic.
    
    Returns:
        JSON response with flashcards organized by Bloom's taxonomy levels
    """
    topic = request.topic.strip()
    logger.info(f"=== Starting flashcard generation for topic: {topic} ===")
    
    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty."
        )
    
    try:
        from langchain_openai import ChatOpenAI
        from app.ca_guidance.agents.flashcard_agent import FlashcardAgent
        
        # Initialize LLM for flashcard generation
        # Use GPT model explicitly for flashcard generation
        model_name = "gpt-4o-mini"  # Use GPT model for flashcard generation
        llm = ChatOpenAI(
            model=model_name,
            api_key=settings.OPENAI_API_KEY,
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
    Save a generated flashcard set to the database with unique IDs.
    
    Returns:
        JSON response with flashcard_set_id and the saved flashcards with IDs
    """
    logger.info(f"=== Saving flashcard set for topic: {request.topic} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        import uuid
        
        client = MongoClient(settings.MONGO_URI)
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
        
        # Create flashcard set document
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
    """
    Submit feedback for a specific flashcard.
    
    Returns:
        JSON response with feedback_id
    """
    logger.info(f"=== Submitting feedback for flashcard {request.flashcard_id} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        
        client = MongoClient(settings.MONGO_URI)
        db = client.ca_guidance
        flashcard_feedback = db.flashcard_feedback
        
        # Create feedback document
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
            "processed": False  # Will be set to True after improvement is applied
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
    """
    Improve a flashcard based on submitted feedback.
    Uses AI to generate improved content and updates the flashcard set.
    
    Returns:
        JSON response with the updated flashcard
    """
    logger.info(f"=== Improving flashcard {request.flashcard_id} based on feedback {request.feedback_id} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from langchain_openai import ChatOpenAI
        from app.core.config import settings
        from app.ca_guidance.agents.flashcard_improvement_agent import FlashcardImprovementAgent
        from pymongo import MongoClient
        
        client = MongoClient(settings.MONGO_URI)
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        flashcard_feedback = db.flashcard_feedback
        
        # Get the feedback document
        feedback_doc = flashcard_feedback.find_one({"_id": ObjectId(request.feedback_id)})
        if not feedback_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Feedback not found"
            )
        
        # Get the flashcard set
        flashcard_set = flashcard_sets.find_one({"_id": ObjectId(request.flashcard_set_id)})
        if not flashcard_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flashcard set not found"
            )
        
        # Find the specific flashcard
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
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flashcard not found in the set"
            )
        
        # Initialize LLM and improvement agent
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=settings.OPENAI_API_KEY,
            temperature=0.3,
        )
        agent = FlashcardImprovementAgent(llm=llm)
        
        # Generate improved flashcard
        improved = agent.improve_flashcard(
            topic=flashcard_set["topic"],
            question=flashcard["question"],
            answer=flashcard["answer"],
            bloom_level=bloom_level,
            feedback_type=feedback_doc.get("feedback_type"),
            comment=feedback_doc.get("comment")
        )
        
        # Update the flashcard in the database
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
        
        # Mark feedback as processed
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


@router.get("/flashcards/topic/{topic}")
async def get_flashcards_by_topic(
    topic: str,
    user: UserInfo = Depends(get_current_user)
):
    """
    Get the latest flashcard set for a topic (returns improved version if available).
    
    Returns:
        JSON response with the flashcard set or 404 if not found
    """
    logger.info(f"=== Getting flashcards for topic: {topic} ===")
    
    try:
        from app.core.config import settings
        from pymongo import MongoClient
        
        client = MongoClient(settings.MONGO_URI)
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        # Get the latest version for this topic
        flashcard_set = flashcard_sets.find_one(
            {"topic": topic, "user_email": user.email},
            sort=[("version", -1)]
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
    """
    Get a flashcard set by ID.
    
    Returns:
        JSON response with the flashcard set
    """
    logger.info(f"=== Getting flashcard set {flashcard_set_id} ===")
    
    try:
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        
        client = MongoClient(settings.MONGO_URI)
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        flashcard_set = flashcard_sets.find_one({"_id": ObjectId(flashcard_set_id)})
        if not flashcard_set:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Flashcard set not found"
            )
        
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
                    "audio_url": existing_reinforced.get("audio_url"),
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
                        "comment": feedback_doc.get("comment")
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
                    "comment": latest_feedback.get("comment")
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
        
        # Generate audio for reinforced summary
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(reinforced_text)
            audio_url = f"/audio/{Path(audio_path).name}"
            logger.info(f"✅ Audio generated for reinforced summary: {audio_url}")
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
        
        logger.info(f"Reinforced summary generated and stored (id: {reinforced_summary_id})")
        
        # Get the stored reinforced summary to get created_at
        stored_reinforced = service.summaries_collection.find_one({"_id": ObjectId(reinforced_summary_id)})
        
        return {
            "summary": reinforced_text,
            "images": images,
            "topic": request.topic,
            "audio_url": audio_url,
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
        
        # Format response
        result = {
            "topic": topic,
            "base": summaries["base"],
            "reinforced": summaries["reinforced"]
        }
        
        logger.info(f"Retrieved summaries for topic '{topic}'")
        return result
        
    except Exception as e:
        logger.error(f"Error getting summaries: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get summaries: {e}"
        )
