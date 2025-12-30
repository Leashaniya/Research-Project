from fastapi import APIRouter
from app.services import generation_service

router = APIRouter()

@router.get("/generate")
async def generate_model_paper():
    # Call the generation service
    output_paths = generation_service.generate_model_paper()

    return {
        "status": "success",
        "output_paths": output_paths
    }