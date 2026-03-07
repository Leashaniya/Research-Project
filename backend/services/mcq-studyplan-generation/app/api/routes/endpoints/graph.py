"""Graph and static file endpoints."""
import os
import sys
from pathlib import Path

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/url", include_in_schema=True)
async def get_graph_url():
    """Return path to graph HTML (frontend prepends base URL)."""
    static_path = SERVICE_ROOT / "static" / "lecture_recommendation_graph.html"
    outputs_path = SERVICE_ROOT / "outputs" / "lecture_recommendation_graph.html"
    if static_path.exists():
        return {"url": "/static/lecture_recommendation_graph.html"}
    if outputs_path.exists():
        return {"url": "/outputs/lecture_recommendation_graph.html"}
    return {"url": None}


@router.get("/static/{path:path}", include_in_schema=False)
async def serve_static(path: str):
    """Serve static files (e.g. graph HTML)."""
    full_path = SERVICE_ROOT / "static" / path
    if full_path.exists() and full_path.is_file():
        return FileResponse(full_path)
    return {"detail": "Not found"}


@router.get("/outputs/{path:path}", include_in_schema=False)
async def serve_outputs(path: str):
    """Serve output files."""
    full_path = SERVICE_ROOT / "outputs" / path
    if full_path.exists() and full_path.is_file():
        return FileResponse(full_path)
    return {"detail": "Not found"}
