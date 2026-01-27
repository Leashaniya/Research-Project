from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.er.render_plan import build_render_plan
from app.er.schemas import ERModel, RenderPlan, ValidationOutput
from app.er.validation import validate_er_model


router = APIRouter(tags=["er"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/validate")
async def validate(model: ERModel) -> ValidationOutput:
    return validate_er_model(model)


@router.post("/render-plan")
async def render_plan(model: ERModel) -> RenderPlan | JSONResponse:
    validation = validate_er_model(model)
    if validation.errors:
        return JSONResponse(status_code=400, content=validation.model_dump())
    return build_render_plan(model)

