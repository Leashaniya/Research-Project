from __future__ import annotations

import logging
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.er.render_plan import build_render_plan
from app.er.schemas import ERModel, RenderPlan, ValidationOutput
from app.er.validation import validate_er_model

logger = logging.getLogger(__name__)

router = APIRouter(tags=["er"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/validate")
async def validate(request: Request) -> ValidationOutput:
    """Validate ER model with detailed error logging."""
    try:
        # Parse body manually to log it
        body_bytes = await request.body()
        body_str = body_bytes.decode('utf-8')
        
        try:
            body_json = json.loads(body_str)
            logger.info(f"Received validation request: {len(body_json.get('entities', []))} entities, {len(body_json.get('relationships', []))} relationships")
            
            # Log relationship details
            if body_json.get('relationships'):
                for i, rel in enumerate(body_json['relationships']):
                    logger.info(f"Relationship {i}: id={rel.get('id')}, name={rel.get('name')}, "
                              f"relationshipType={rel.get('relationshipType', 'MISSING')}, "
                              f"fromEntityId={rel.get('fromEntityId')}, toEntityId={rel.get('toEntityId')}")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in request body: {body_str[:500]}")
        
        # Try to parse as ERModel
        try:
            data = json.loads(body_str)
            model = ERModel(**data)
            return validate_er_model(model)
        except ValidationError as e:
            logger.error("=" * 80)
            logger.error("PYDANTIC VALIDATION ERROR:")
            logger.error(json.dumps(e.errors(), indent=2))
            logger.error("=" * 80)
            raise HTTPException(status_code=422, detail=e.errors())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in validate endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/render-plan", response_model=None)
async def render_plan(model: ERModel):
    validation = validate_er_model(model)
    if validation.errors:
        return JSONResponse(status_code=400, content=validation.model_dump())
    return build_render_plan(model)

