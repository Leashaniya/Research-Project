import logging
import urllib.parse
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR

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
    Public endpoint to serve images from the RAG extracted images directory.
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
        
        # Resolve to absolute path to ensure we're looking in the right place
        image_output_dir_abs = IMAGE_OUTPUT_DIR.resolve()
        
        if not image_output_dir_abs.exists():
            error_msg = f"IMAGE_OUTPUT_DIR does not exist: {image_output_dir_abs}"
            logger.error(error_msg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Image directory does not exist: {image_output_dir_abs}"
            )
        
        # Try exact match first
        image_path = image_output_dir_abs / decoded_name
        
        # Try case-insensitive match if not found
        if not image_path.exists():
            decoded_lower = decoded_name.lower()
            available_files = [f for f in image_output_dir_abs.glob("*") if f.is_file()]
            
            for img_file in available_files:
                if img_file.name.lower() == decoded_lower:
                    image_path = img_file
                    break
            
            # If still not found, try partial match (filename might have been truncated)
            if not image_path.exists():
                base_name = decoded_name.rsplit('.', 1)[0].lower()
                for img_file in available_files:
                    file_base = img_file.name.rsplit('.', 1)[0].lower()
                    # Check if the requested name is contained in the file name or vice versa
                    if base_name in file_base or file_base in base_name:
                        # Prefer exact or longer matches
                        if len(file_base) >= len(base_name) * 0.8:  # At least 80% match
                            image_path = img_file
                            break
        
        if not image_path.exists():
            available_files = [f.name for f in image_output_dir_abs.glob("*") if f.is_file()]
            logger.error(f"Image not found: {decoded_name}. Available files: {len(available_files)} files in directory.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=f"Image not found: {decoded_name}. Available files: {len(available_files)} files in directory."
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

