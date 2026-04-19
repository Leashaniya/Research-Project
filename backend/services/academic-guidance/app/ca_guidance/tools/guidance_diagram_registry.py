"""
Per-request registry of diagram PNGs generated during CA guidance (ER, flowchart, general).

Used to map invented image names to real ``guidance_*.png`` files and to build short
captions from each tool call's ``description`` (question context).
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import List, Optional, Tuple

_entries: ContextVar[Optional[List[Tuple[str, str]]]] = ContextVar(
    "guidance_diagram_registry_entries", default=None
)


def begin_guidance_diagram_registry() -> None:
    """Start collecting (filename, description) pairs for the current guidance request."""
    _entries.set([])


def register_guidance_diagram_png(filename: str, description: str) -> None:
    """Record a guidance PNG under generated_images (ER, flowchart, or general)."""
    bucket = _entries.get()
    if bucket is None:
        return
    fname = (filename or "").strip()
    if not (
        fname.startswith("guidance_er_diagram_")
        or fname.startswith("guidance_flowchart_")
        or fname.startswith("guidance_general_")
    ):
        return
    bucket.append((fname, (description or "")[:5000]))


def register_guidance_er_diagram(filename: str, description: str) -> None:
    """Backward-compatible alias for ER-only registration."""
    register_guidance_diagram_png(filename, description)


def get_guidance_diagram_registry() -> List[Tuple[str, str]]:
    """Return a copy of registered diagrams in generation order."""
    b = _entries.get()
    return list(b) if b else []


def end_guidance_diagram_registry() -> None:
    """Clear the registry (call in ``finally`` after guidance image processing)."""
    _entries.set(None)
