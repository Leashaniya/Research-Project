from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services import pipeline_service

router = APIRouter()

class PipelineRequest(BaseModel):
    action: str
    payload: dict = {}

@router.post("/run")
async def run_pipeline(request: PipelineRequest):
    action = request.action
    payload = request.payload

    # Validate action
    valid_actions = ["past_paper", "slides", "structure", "generate_model_paper"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}")

    # Run the pipeline
    result = pipeline_service.run_pipeline(action, payload)

    return {
        "status": "success",
        "action": action,
        "result": result
    }