"""Graph and static file endpoints."""
import json
import os
import sys
from pathlib import Path

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter
from fastapi.responses import FileResponse
from app.services import state
from weak_topic_rag import generate_weak_topic_rag_summary

router = APIRouter()
router_weak = APIRouter()

_RECOMMENDATIONS_JSON = SERVICE_ROOT / "outputs" / "graphrag_recommendations.json"
_STUDENT_CONTEXT_JSON = SERVICE_ROOT / "outputs" / "student_learning_context.json"


@router.get("/student-context", include_in_schema=True)
async def get_graph_student_context():
    """
    Last saved GraphRAG learning-map summary (after analysis / graph build).
    Used by the React UI for adaptive-plan explanations — no extra computation.
    """
    if _STUDENT_CONTEXT_JSON.is_file():
        try:
            with open(_STUDENT_CONTEXT_JSON, "r", encoding="utf-8") as f:
                context = json.load(f)
            return {
                "available": True,
                "student_learning_context": context,
                "weak_topics_confirmed": context.get("weak_topics_confirmed", []),
                "related_concept_links": [
                    {
                        "from_weak": item.get("weak_topic", ""),
                        "related_concept": item.get("related_topic", ""),
                        "link_type": item.get("link_type", ""),
                    }
                    for item in (context.get("related_topics") or [])
                ],
                "student_map_summary": {
                    "weak_topics": context.get("weak_topics_confirmed", []),
                    "related_concepts": [t.get("related_topic") for t in (context.get("related_topics") or []) if t.get("related_topic")],
                    "practice_count": len(context.get("recommended_mcqs", [])),
                    "uses_graphrag_topic_links": bool(context.get("related_topics")),
                },
                "recommendation_reason_traces": [
                    {
                        "question_id": item.get("question_id", ""),
                        "reason_trace": item.get("reason_trace", {}),
                    }
                    for item in (context.get("recommended_mcqs") or [])
                ],
                "uses_confirmed_weak_topics": bool(context.get("weak_topics_confirmed")),
                "meta": {
                    "has_quiz_state": True,
                    "priority_files": context.get("priority_lectures", []),
                },
            }
        except (json.JSONDecodeError, OSError):
            pass

    if not _RECOMMENDATIONS_JSON.is_file():
        return {
            "available": False,
            "meta": {},
            "related_concept_links": [],
        }
    try:
        with open(_RECOMMENDATIONS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "available": False,
            "meta": {},
            "related_concept_links": [],
        }
    meta = data.get("meta") or {}
    return {
        "available": True,
        "student_learning_context": meta.get("student_learning_context", {}),
        "weak_topics_confirmed": meta.get("weak_topics_confirmed", []),
        "related_concept_links": (meta.get("related_concept_links", []) + meta.get("prerequisite_concept_links", [])),
        "student_map_summary": meta.get("student_map_summary", {}),
        "recommendation_reason_traces": [
            {
                "question_id": item.get("question_id", ""),
                "reason_trace": item.get("reason_trace", {}),
            }
            for item in (data.get("recommendations") or [])[:20]
        ],
        "uses_confirmed_weak_topics": meta.get("uses_confirmed_weak_topics", False),
        "meta": {
            "has_quiz_state": meta.get("has_quiz_state"),
            "priority_files": meta.get("priority_files", []),
        },
    }


@router.get("/url", include_in_schema=True)
async def get_graph_url():
    """Return path to graph HTML (frontend prepends base URL).
    Prefer GraphRAG visualization when present; fall back to legacy lecture graph."""
    graphrag_outputs = SERVICE_ROOT / "outputs" / "graphrag_visualization.html"
    graphrag_static = SERVICE_ROOT / "static" / "graphrag_visualization.html"
    legacy_static = SERVICE_ROOT / "static" / "lecture_recommendation_graph.html"
    legacy_outputs = SERVICE_ROOT / "outputs" / "lecture_recommendation_graph.html"
    if graphrag_outputs.exists():
        return {"url": "/outputs/graphrag_visualization.html"}
    if graphrag_static.exists():
        return {"url": "/static/graphrag_visualization.html"}
    if legacy_static.exists():
        return {"url": "/static/lecture_recommendation_graph.html"}
    if legacy_outputs.exists():
        return {"url": "/outputs/lecture_recommendation_graph.html"}
    return {"url": None}


@router.get("/static/{path:path}", include_in_schema=False)
async def serve_static(path: str):
    """Serve static files (e.g. graph HTML)."""
    full_path = SERVICE_ROOT / "static" / path
    if full_path.exists() and full_path.is_file():
        response = FileResponse(full_path)
        if str(full_path).lower().endswith(".html"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    return {"detail": "Not found"}


@router.get("/outputs/{path:path}", include_in_schema=False)
async def serve_outputs(path: str):
    """Serve output files."""
    full_path = SERVICE_ROOT / "outputs" / path
    if full_path.exists() and full_path.is_file():
        response = FileResponse(full_path)
        if str(full_path).lower().endswith(".html"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response
    return {"detail": "Not found"}


@router_weak.get("/weak-topic-summary", include_in_schema=True)
async def get_weak_topic_summary():
    """Lightweight RAG summary for confirmed weak topics."""
    if not state.LECTURE_DATA:
        return {"weak_topic_summary": []}
    return generate_weak_topic_rag_summary(state.LECTURE_DATA)
