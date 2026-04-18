# tools/diagram_image_tool.py
"""Generate assignment-related diagram images (ER, flowchart, etc.) for CA guidance."""

import base64
import logging
import re
import uuid
from pathlib import Path

from crewai.tools import tool
from openai import OpenAI

from app.core.config import settings
from app.ca_guidance.rag.config.settings import GENERATED_IMAGE_OUTPUT_DIR

logger = logging.getLogger(__name__)


def _normalize_diagram_type(diagram_type: str) -> str:
    s = (diagram_type or "").strip().lower().replace(" ", "_").replace("-", "_")
    er_aliases = (
        "er_diagram",
        "erd",
        "eerd",
        "entity_relationship",
        "er",
        "er_model",
        "eer",
        "eer_diagram",
    )
    flow_aliases = ("flowchart", "flow_chart", "process_diagram", "process_flow")
    if s in er_aliases:
        return "er_diagram"
    if s in flow_aliases:
        return "flowchart"
    if s == "general":
        return "general"
    if "erd" in s or "eerd" in s or "er_diagram" in s:
        return "er_diagram"
    if "flowchart" in s or "flow_chart" in s:
        return "flowchart"
    return "general"


def _build_image_prompt(diagram_type: str, description: str) -> str:
    desc = (description or "").strip()
    if len(desc) > 2800:
        desc = desc[:2800] + "…"

    if diagram_type == "flowchart":
        return (
            "Professional technical flowchart on a plain white background, top-to-bottom or left-to-right. "
            "Rounded rectangles for steps, clear arrows, readable English labels. "
            "Black outlines, minimal gray shading. No decorative art. "
            "The flowchart must reflect this process or workflow:\n"
            f"{desc}"
        )
    return (
        "Clear technical diagram on a plain white background suitable for a DBMS assignment handout. "
        "Black outlines, readable English labels, no decorative clutter. "
        "Illustrate the following:\n"
        f"{desc}"
    )


def _get_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")
    try:
        import httpx

        return OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=httpx.Timeout(120.0, connect=15.0),
        )
    except ImportError:
        return OpenAI(api_key=settings.OPENAI_API_KEY)


def _sanitize_filename_base(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", (name or "diagram").strip())[:80].strip("_")
    return base or "diagram"


@tool("Generate Assignment Diagram Image")
def generate_assignment_diagram(diagram_type: str, description: str) -> str:
    """
    Produce a diagram for assignment / lab visuals.

    - **ER / EER / conceptual ER**: builds conceptual Graphviz DOT and renders it to a PNG.
      Paste the returned `[IMAGE:filename.png]` line in markdown.
    - **Flowchart / general**: generates a **PNG** via OpenAI Images API; paste the exact `[IMAGE:filename.png]`
      line returned (outside code fences).

    Args:
        diagram_type: One of: "er_diagram", "flowchart", or "general" (synonyms like "ERD" are OK).
        description: For ER: entities, relationships, attributes, and cardinalities from the question.
            For flowchart/general: process steps or what to illustrate.

    Returns:
        Instructions including the exact `[IMAGE:...]` reference to embed in markdown.
    """
    kind = _normalize_diagram_type(diagram_type)
    if not (description or "").strip():
        return (
            "No description was provided for the diagram. Summarize entities/relationships "
            "or process steps from the assignment question, then call this tool again with a non-empty description."
        )

    if kind == "er_diagram":
        try:
            from app.ca_guidance.tools.graphviz_er import (
                generate_conceptual_er_dot,
                render_dot_to_png,
            )

            dot = generate_conceptual_er_dot(description)
            image_bytes = render_dot_to_png(dot)
            GENERATED_IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            fname = f"guidance_er_diagram_{uuid.uuid4().hex[:10]}.png"
            out_path = GENERATED_IMAGE_OUTPUT_DIR / fname
            out_path.write_bytes(image_bytes)
            logger.info("Saved conceptual ER diagram image to %s", out_path)
            return (
                f"Generated conceptual ER diagram image saved as `{fname}`.\n\n"
                "Include this **exact** line in your markdown next to your explanation (outside code fences):\n\n"
                f"[IMAGE:{fname}]\n\n"
                "Optional: you may also add a short explanation of entities, relationships, attributes, and cardinality."
            )
        except Exception as e:
            logger.error("Conceptual ER diagram generation/render failed: %s", e, exc_info=True)
            return (
                f"Could not generate conceptual ER diagram image ({e}). "
                "Draw a conceptual ER diagram manually in Graphviz DOT or Mermaid inside a fenced code block, "
                "with rectangles for entities, a diamond or labeled relationship for each relationship set, "
                "ovals for key attributes, and cardinality on each edge."
            )

    if not getattr(settings, "ENABLE_ASSIGNMENT_DIAGRAM_IMAGES", True):
        return (
            "PNG diagram image generation is disabled. Provide Graphviz DOT or Mermaid "
            "inside a markdown fenced code block instead."
        )

    prompt = _build_image_prompt(kind, description)
    model = getattr(settings, "ASSIGNMENT_DIAGRAM_IMAGE_MODEL", "dall-e-3")

    try:
        client = _get_client()
        image_bytes: bytes | None = None

        try:
            gen_kwargs = {
                "model": model,
                "prompt": prompt,
                "n": 1,
                "size": "1024x1024",
                "response_format": "b64_json",
            }
            if model == "dall-e-3":
                gen_kwargs["quality"] = "standard"
            resp = client.images.generate(**gen_kwargs)
            b64 = resp.data[0].b64_json if resp.data else None
            if b64:
                image_bytes = base64.standard_b64decode(b64)
        except Exception as e1:
            logger.warning("Primary image model failed (%s): %s; trying dall-e-2", model, e1)
            if model != "dall-e-2":
                resp2 = client.images.generate(
                    model="dall-e-2",
                    prompt=prompt[:900],
                    n=1,
                    size="512x512",
                    response_format="b64_json",
                )
                b64 = resp2.data[0].b64_json if resp2.data else None
                if b64:
                    image_bytes = base64.standard_b64decode(b64)

        if not image_bytes:
            return (
                "Image generation did not return image data. Provide a Mermaid or ASCII diagram "
                "in a fenced code block as a fallback."
            )

        GENERATED_IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        short = _sanitize_filename_base(kind)
        fname = f"guidance_{short}_{uuid.uuid4().hex[:10]}.png"
        out_path = GENERATED_IMAGE_OUTPUT_DIR / fname
        out_path.write_bytes(image_bytes)
        logger.info("Saved assignment diagram image to %s", out_path)

        alt = f"{kind.replace('_', ' ').title()} for assignment"
        return (
            f"Generated diagram image saved as `{fname}`.\n\n"
            "Include this **exact** line in your markdown next to your explanation (outside code fences):\n\n"
            f"[IMAGE:{fname}]\n\n"
            f"Optional caption line: ![{alt}]({fname})\n"
        )
    except Exception as e:
        logger.error("generate_assignment_diagram failed: %s", e, exc_info=True)
        return (
            f"Could not generate diagram image ({e}). "
            "Provide a clear Mermaid or ASCII diagram inside a markdown fenced code block instead."
        )
