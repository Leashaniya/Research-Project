from fastapi import APIRouter, HTTPException
from app.services import pipeline_service

router = APIRouter()

@router.get("/generate")
async def generate_model_paper():
    try:
        return await pipeline_service.run_full_pipeline()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
