import logging
import urllib.parse
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR, GENERATED_IMAGE_OUTPUT_DIR

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["public"])

@router.get("/")
async def root():
    return {"message": "Welcome to CA Guidance & Summarization API", "version": "1.0.0"}

@router.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API is running"}

@router.get("/images/{image_name:path}")
async def get_image(image_name: str):
    """
    Public endpoint to serve images from RAG image directories.
    No authentication required.
    
    Args:
        image_name: Name of the image file to serve (can include path segments)
        
    Returns:
        Image file response
    """
    try:
        # URL decode the image name
        decoded_name = urllib.parse.unquote(image_name)
        
        # Security: Only allow image files
        if not decoded_name.lower().endswith(('.jpeg', '.jpg', '.png', '.gif')):
            logger.error(f"Invalid file type: {decoded_name}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid image file type")
        
        image_dirs = [GENERATED_IMAGE_OUTPUT_DIR.resolve(), IMAGE_OUTPUT_DIR.resolve()]
        image_path = None
        available_files = []

        for image_dir_abs in image_dirs:
            if not image_dir_abs.exists():
                continue

            # Try exact match first
            candidate = image_dir_abs / decoded_name
            if candidate.exists():
                image_path = candidate
                break

            # Try case-insensitive / partial match if not found
            decoded_lower = decoded_name.lower()
            files_in_dir = [f for f in image_dir_abs.glob("*") if f.is_file()]
            available_files.extend([f.name for f in files_in_dir])

            for img_file in files_in_dir:
                if img_file.name.lower() == decoded_lower:
                    image_path = img_file
                    break
            if image_path:
                break

            base_name = decoded_name.rsplit('.', 1)[0].lower()
            for img_file in files_in_dir:
                file_base = img_file.name.rsplit('.', 1)[0].lower()
                if base_name in file_base or file_base in base_name:
                    if len(file_base) >= len(base_name) * 0.8:
                        image_path = img_file
                        break
            if image_path:
                break

        if not image_path or not image_path.exists():
            logger.error(f"Image not found: {decoded_name}. Available files across image dirs: {len(available_files)}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Image not found: {decoded_name}. Available files: {len(available_files)}"
            )
        
        # Determine media type based on actual file extension
        media_type = "image/jpeg"
        if image_path.name.lower().endswith('.png'):
            media_type = "image/png"
        elif image_path.name.lower().endswith('.gif'):
            media_type = "image/gif"
        
        return FileResponse(
            path=str(image_path.resolve()),
            media_type=media_type,
            filename=image_path.name
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving image {image_name}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to serve image: {str(e)}"
        )

