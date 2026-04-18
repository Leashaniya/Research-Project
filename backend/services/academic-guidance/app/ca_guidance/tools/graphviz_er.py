"""LLM-generated conceptual ER diagrams as Graphviz DOT and PNG rendering."""

import json
import logging
import re

import requests

from app.core.config import settings
from app.er.schemas import ERModel
from app.er.validation import validate_er_model

logger = logging.getLogger(__name__)


def _get_openai_client():
    from openai import OpenAI

    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not configured")
    try:
        import httpx

        return OpenAI(
            api_key=settings.OPENAI_API_KEY,
            timeout=httpx.Timeout(90.0, connect=15.0),
        )
    except ImportError:
        return OpenAI(api_key=settings.OPENAI_API_KEY)


def _strip_wrapping_fences(text: str) -> str:
    t = (text or "").strip()
    m = re.match(r"^```(?:dot|graphviz|json)?\s*\n?([\s\S]*?)\n?```\s*$", t, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return t


def _ensure_graph_boundaries(dot: str) -> str:
    body = (dot or "").strip()
    if not body.lower().startswith("graph "):
        if "{" not in body or "}" not in body:
            body = f'graph ER {{\n{body}\n}}'
    if "{" not in body or "}" not in body:
        raise ValueError("DOT output missing graph boundaries")
    return body


def _slug(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip())
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "X"
    if s[0].isdigit():
        s = f"N_{s}"
    return s


def _safe_label(text: str) -> str:
    return (text or "").replace('"', '\\"')


def _er_model_to_dot(model: ERModel) -> str:
    """
    Convert validated ERModel to conceptual Chen-style Graphviz DOT.
    """
    lines: list[str] = []
    lines.append("graph ER {")
    lines.append("  rankdir=LR;")
    lines.append('  graph [splines=true, overlap=false, fontname="Helvetica"];')
    lines.append('  node [fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica"];')

    entity_id_to_node: dict[str, str] = {}
    rel_id_to_node: dict[str, str] = {}

    # Entities
    for e in model.entities:
        nid = f"E_{_slug(e.id)}"
        entity_id_to_node[e.id] = nid
        shape = "ellipse" if e.isWeak else "box"
        lines.append(f'  {nid} [shape={shape}, label="{_safe_label(e.name)}"];')

        # Entity attributes as separate ovals
        for a in e.attributes:
            aid = f"A_{_slug(e.id)}_{_slug(a.id)}"
            label = a.name
            if a.pk:
                label = f"{label} (PK)"
            if a.type == "multivalued":
                label = f"{label} (multivalued)"
            if a.type == "composite":
                label = f"{label} (composite)"
            lines.append(f'  {aid} [shape=ellipse, label="{_safe_label(label)}"];')
            lines.append(f"  {nid} -- {aid};")
            for sub in (a.subAttributes or []):
                sid = f"S_{_slug(e.id)}_{_slug(a.id)}_{_slug(sub.id)}"
                lines.append(f'  {sid} [shape=ellipse, label="{_safe_label(sub.name)}"];')
                lines.append(f"  {aid} -- {sid};")

    # Relationships
    for r in model.relationships:
        # Aggregation container: render inner relationships only
        if r.relationshipType == "aggregation":
            whole = entity_id_to_node.get(r.aggregationWholeEntityId or "")
            for ar in (r.aggregationRelationships or []):
                part = entity_id_to_node.get(ar.partEntityId or "")
                if not whole or not part:
                    continue
                rid = f"R_{_slug(r.id)}_{_slug(ar.id)}"
                lines.append(f'  {rid} [shape=diamond, label="{_safe_label(ar.name)}"];')
                if ar.direction == "part_to_whole":
                    lines.append(f'  {part} -- {rid} [label="{_safe_label(ar.cardinality)}"];')
                    lines.append(f'  {whole} -- {rid} [label="1..1"];')
                else:
                    lines.append(f'  {whole} -- {rid} [label="1..1"];')
                    lines.append(f'  {part} -- {rid} [label="{_safe_label(ar.cardinality)}"];')
            continue

        rid = f"R_{_slug(r.id)}"
        rel_id_to_node[r.id] = rid
        rel_label = "ISA" if r.relationshipType == "isa" else r.name
        lines.append(f'  {rid} [shape=diamond, label="{_safe_label(rel_label)}"];')

        if r.relationshipType == "isa":
            parent = entity_id_to_node.get(r.parentEntityId or "")
            if parent:
                lines.append(f'  {parent} -- {rid} [label="{ "total" if r.isTotal else "partial" }"];')
            for child in (r.childEntityIds or []):
                c = entity_id_to_node.get(child)
                if c:
                    lines.append(f'  {c} -- {rid} [label="{ "disjoint" if r.isDisjoint else "overlap" }"];')
        else:
            e_from = entity_id_to_node.get(r.fromEntityId)
            e_to = entity_id_to_node.get(r.toEntityId)
            if e_from:
                lines.append(f'  {e_from} -- {rid} [label="{_safe_label(r.fromCardinality)}"];')
            if e_to:
                lines.append(f'  {e_to} -- {rid} [label="{_safe_label(r.toCardinality)}"];')
            if r.relationshipType == "ternary" and r.thirdEntityId:
                e_third = entity_id_to_node.get(r.thirdEntityId)
                if e_third:
                    third_card = r.thirdCardinality or "1..1"
                    lines.append(f'  {e_third} -- {rid} [label="{_safe_label(third_card)}"];')

        # Relationship attributes
        for a in r.attributes:
            aid = f"AR_{_slug(r.id)}_{_slug(a.id)}"
            label = a.name
            if a.pk:
                label = f"{label} (PK)"
            if a.type == "multivalued":
                label = f"{label} (multivalued)"
            if a.type == "composite":
                label = f"{label} (composite)"
            lines.append(f'  {aid} [shape=ellipse, label="{_safe_label(label)}"];')
            lines.append(f"  {rid} -- {aid};")

    lines.append("}")
    return "\n".join(lines)


def generate_conceptual_er_dot(description: str) -> str:
    """
    Generate conceptual ER diagram source in Graphviz DOT.
    """
    desc = (description or "").strip()
    if len(desc) > 6000:
        desc = desc[:6000] + "..."

    model = getattr(settings, "ASSIGNMENT_ER_GRAPHVIZ_MODEL", "gpt-4o-mini")
    system = """You output ONLY valid JSON for an ERModel object.

Rules:
- Match this schema strictly:
  {
    "entities": [ { "id","name","attributes":[...],"isWeak", "strongEntityId" } ],
    "relationships": [ { "id","name","relationshipType", ...fields... } ]
  }
- Use relationshipType among: binary, ternary, isa, aggregation.
- IMPORTANT: include required base fields on every relationship object: fromEntityId, toEntityId, fromCardinality, toCardinality
  (even for isa/aggregation, set them consistently to existing entities and valid cardinalities).
- Cardinalities MUST be one of: "0..1", "1..1", "0..*", "1..*".
- For ISA: set parentEntityId, childEntityIds, isDisjoint, isTotal.
- For aggregation: set aggregationWholeEntityId, aggregationPartEntityIds, aggregationRelationships.
- Attributes must be listed separately in entity/relationship attributes arrays, not embedded in names.
- Do NOT use Crow's Foot. Conceptual Chen semantics only.
- Return JSON only, no markdown fences, no commentary.
"""

    user_base = (
        "Build a conceptual ERModel JSON from this assignment text. "
        "Extract entities, relationships, attributes, and cardinalities. "
        "Keep attributes as explicit attribute objects linked to entities/relationships by ownership, "
        "and avoid Crow's Foot notation.\n\n"
        f"{desc}"
    )

    client = _get_openai_client()
    extra_feedback = ""
    last_errors: list[str] = []
    for attempt in range(3):
        user = user_base
        if extra_feedback:
            user += "\n\nIMPORTANT CORRECTIONS FROM PREVIOUS ATTEMPT:\n" + extra_feedback

        resp = client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        raw = (resp.choices[0].message.content or "").strip()
        json_text = _strip_wrapping_fences(raw)
        model_errors: list[str] = []
        dot = ""
        try:
            data = json.loads(json_text)
            er_model = ERModel(**data)
            validation = validate_er_model(er_model)
            if validation.errors:
                model_errors.extend([f"{i.code}: {i.message} @ {i.path}" for i in validation.errors[:8]])
            else:
                dot = _er_model_to_dot(er_model)
                dot = _ensure_graph_boundaries(dot)
        except Exception as parse_err:
            model_errors.append(f"Invalid ERModel JSON: {parse_err}")

        all_errors = model_errors
        if not all_errors:
            logger.info("Generated conceptual ER Graphviz DOT (%d chars)", len(dot))
            return dot

        last_errors = all_errors
        extra_feedback = "\n".join(f"- {e}" for e in all_errors)
        logger.warning("Graphviz DOT attempt %d failed validation: %s", attempt + 1, all_errors)

    raise ValueError("Generated DOT failed conceptual ER validation: " + "; ".join(last_errors))


def render_dot_to_png(dot_source: str) -> bytes:
    """
    Render Graphviz DOT to PNG bytes using a Graphviz HTTP renderer.
    """
    source = (dot_source or "").strip()
    if not source:
        raise ValueError("Graphviz DOT source is empty")

    render_url = getattr(settings, "GRAPHVIZ_RENDER_URL", "https://kroki.io/graphviz/png")
    resp = requests.post(
        render_url,
        data=source.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8"},
        timeout=45,
    )
    if not resp.ok:
        raise RuntimeError(f"Graphviz render failed ({resp.status_code}): {resp.text[:200]}")
    content_type = (resp.headers.get("Content-Type") or "").lower()
    if "image/png" not in content_type:
        raise RuntimeError(f"Unexpected Graphviz renderer content type: {content_type}")
    return resp.content
