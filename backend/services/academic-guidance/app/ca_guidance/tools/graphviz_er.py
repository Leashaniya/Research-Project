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


def _html_escape(s: str) -> str:
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _attribute_label_html(attr) -> str:
    """Graphviz HTML-like label: attribute name only (PK underlined). Type is shown by shape (double oval = multivalued)."""
    name = _html_escape(attr.name)
    if attr.pk:
        core = f"<u>{name}</u>"
    else:
        core = name
    return f"<{core}>"


def _er_model_to_dot(model: ERModel) -> str:
    """
    Convert validated ERModel to conceptual Chen-style Graphviz DOT.
    Entities: rectangles. Attributes: ovals (multivalued = double oval / peripheries=2).
    Relationships: diamonds. ISA: triangle. Weak entities: double rectangle.
    Aggregation: inner relationship diamond(s) inside a dashed subgraph cluster.
    """
    lines: list[str] = []
    lines.append("graph ER {")
    lines.append("  rankdir=LR;")
    lines.append(
        '  graph [splines=true, overlap=false, fontname="Helvetica", '
        'nodesep=0.9, ranksep=1.1, sep="+10,10"];'
    )
    lines.append('  node [fontname="Helvetica"];')
    lines.append('  edge [fontname="Helvetica"];')

    entity_id_to_node: dict[str, str] = {}
    rel_id_to_node: dict[str, str] = {}

    def _emit_attr_oval(prefix_indent: str, aid: str, attr) -> None:
        lab = _attribute_label_html(attr)
        extra = ", peripheries=2" if attr.type == "multivalued" else ""
        lines.append(f"{prefix_indent}{aid} [shape=ellipse, label={lab}{extra}];")

    def _emit_entity_attributes(prefix_indent: str, eid: str, nid: str, attrs: list) -> None:
        for a in attrs:
            aid = f"A_{_slug(eid)}_{_slug(a.id)}"
            _emit_attr_oval(prefix_indent, aid, a)
            lines.append(f"{prefix_indent}{nid} -- {aid};")
            for sub in a.subAttributes or []:
                sid = f"S_{_slug(eid)}_{_slug(a.id)}_{_slug(sub.id)}"
                _emit_attr_oval(prefix_indent, sid, sub)
                lines.append(f"{prefix_indent}{aid} -- {sid};")

    # Strong entities (rectangles)
    for e in model.entities:
        if e.isWeak:
            continue
        nid = f"E_{_slug(e.id)}"
        entity_id_to_node[e.id] = nid
        lines.append(f'  {nid} [shape=box, label="{_safe_label(e.name)}"];')
        _emit_entity_attributes("  ", e.id, nid, e.attributes)

    # Weak entities: double-line rectangle (Chen); attributes as ovals linked to the entity
    for e in model.entities:
        if not e.isWeak:
            continue
        nid = f"E_{_slug(e.id)}"
        entity_id_to_node[e.id] = nid
        lines.append(f'  {nid} [shape=box, peripheries=2, label="{_safe_label(e.name)}"];')
        _emit_entity_attributes("  ", e.id, nid, e.attributes)

    # Relationships
    for r in model.relationships:
        # Aggregation: dashed cluster around inner relationship diamond(s) and their attributes
        if r.relationshipType == "aggregation":
            whole = entity_id_to_node.get(r.aggregationWholeEntityId or "")
            inner: list[tuple] = []
            for ar in r.aggregationRelationships or []:
                part = entity_id_to_node.get(ar.partEntityId or "")
                if not whole or not part:
                    continue
                rid = f"R_{_slug(r.id)}_{_slug(ar.id)}"
                inner.append((ar, part, rid))
            if inner:
                cid = f"cluster_agg_{_slug(r.id)}"
                lines.append(f"  subgraph {cid} {{")
                lines.append("    style=dashed;")
                lines.append("    color=dimgray;")
                lines.append('    fontname="Helvetica";')
                lines.append('    label="";')
                for ar, _part, rid in inner:
                    lines.append(f'    {rid} [shape=diamond, label="{_safe_label(ar.name)}"];')
                    for a in ar.attributes or []:
                        aid = f"AR_{_slug(r.id)}_{_slug(ar.id)}_{_slug(a.id)}"
                        _emit_attr_oval("    ", aid, a)
                        lines.append(f"    {rid} -- {aid};")
                lines.append("  }")
                for ar, part, rid in inner:
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
        if r.relationshipType == "isa":
            # Chen-style ISA / subset: triangle (not diamond); parent above, children linked to triangle
            lines.append(
                f'  {rid} [shape=triangle, fixedsize=true, width=0.55, height=0.5, '
                f'label="{_safe_label(rel_label)}"];'
            )
        else:
            lines.append(f'  {rid} [shape=diamond, label="{_safe_label(rel_label)}"];')

        if r.relationshipType == "isa":
            # One parent (supertype) to triangle; triangle to each subtype. No edge labels (reduces clutter/overlap).
            parent = entity_id_to_node.get(r.parentEntityId or "")
            if parent:
                lines.append(f"  {parent} -- {rid};")
            for child in (r.childEntityIds or []):
                c = entity_id_to_node.get(child)
                if c:
                    lines.append(f"  {rid} -- {c};")
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

        # Descriptive (relationship) attributes: ovals connected to the relationship diamond
        if r.relationshipType == "isa":
            continue
        for a in r.attributes:
            aid = f"AR_{_slug(r.id)}_{_slug(a.id)}"
            _emit_attr_oval("  ", aid, a)
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
- For aggregation: set aggregationWholeEntityId, aggregationPartEntityIds, aggregationRelationships (inner diamonds + part entities).
- Entities: rectangles. Relationships: diamonds. Attributes: NEVER inside entity boxes—each attribute is its own object with pk/type/subAttributes.
- Primary keys: set pk=true on key attributes (rendered underlined in the diagram).
- Multivalued attributes: type "multivalued" (double-line oval in the diagram).
- Composite attributes: type "composite" with subAttributes for parts (e.g. Address → Street, City).
- Descriptive attributes: attributes that describe a relationship belong in that relationship's attributes array.
- Binary: two entities to one diamond. Ternary: three entities to one diamond (thirdEntityId + thirdCardinality).
- Weak entities: isWeak=true, strongEntityId; diagram uses double-line rectangle for the weak entity.
- ISA: relationshipType "isa", label conceptually "ISA"; parent + children entities.
- Do NOT use Crow's Foot. Conceptual Chen semantics only.
- ATTRIBUTE OBJECTS (critical): every attribute MUST include id, name, pk (boolean), unique (boolean), nullable (boolean),
  and type MUST be exactly one of: "regular", "composite", "multivalued" only.
  Never use SQL or domain types (string, int, integer, date, varchar, etc.) as the value of "type"—those are not allowed.
- Return JSON only, no markdown fences, no commentary.
"""

    user_base = (
        "=== ASSIGNMENT / QUESTION CONTEXT (single source of truth for the diagram) ===\n"
        f"{desc}\n"
        "=== END CONTEXT ===\n\n"
        "Build ONE complete ERModel JSON for EXACTLY the scenario in the context block above.\n"
        "- Entity names, relationship names, and attributes MUST reflect that context. "
        "Do not swap in unrelated textbook examples unless the same concepts are clearly present in the context.\n"
        "- Do not invent major entities or relationships that are not stated or clearly implied by the context.\n"
        "- If the context is a single exam question, model only what that question asks for.\n"
        "- Identify every entity, relationship (binary/ternary/ISA/aggregation), attribute (including multivalued, composite, "
        "and relationship-descriptive), and cardinality as stated or reasonably implied from the context.\n"
        "- Every relationship diamond must connect only to entities that participate in that relationship in the context.\n"
    )

    client = _get_openai_client()
    extra_feedback = ""
    last_errors: list[str] = []
    for attempt in range(3):
        user = user_base
        if extra_feedback:
            user += (
                "\n\nIMPORTANT CORRECTIONS FROM PREVIOUS ATTEMPT (fix schema/IDs only; "
                "keep the same real-world scenario as in the context block above):\n"
                + extra_feedback
            )

        resp = client.chat.completions.create(
            model=model,
            temperature=0.1,
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
