import html
import io
import fitz  # PyMuPDF
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse, quote

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models.schemas import (
    UserInfo, 
    SummarizeRequest,
    SummaryFeedbackRequest,
    ReinforceSummaryRequest,
    SummaryResponse,
    FeedbackResponse,
    SaveFlashcardSetRequest,
    FlashcardFeedbackRequest,
    FlashcardUpdateRequest,
    GuidanceFeedbackRequest,
    ReinforceGuidanceRequest,
    GuidancePdfRequest,
)
from app.ca_guidance.crew import create_guidance_crew, create_summarization_crew
from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR, GENERATED_IMAGE_OUTPUT_DIR
from app.ca_guidance.tools.tts_tool import text_to_speech_wav  # ✅ AUDIO
from app.ca_guidance.tools.rag_tool import (
    _get_rag_chain,
    _extract_context_text,
    _verify_summary_accuracy,
    verify_guidance_accuracy
)

logger = logging.getLogger(__name__)


def _short_guidance_image_caption(text: str, max_len: int = 185) -> str:
    """One-line caption for under-image display (plain text, will be HTML-escaped later)."""
    if not (text or "").strip():
        return ""
    s = re.sub(r"\s+", " ", text.strip())
    if len(s) <= max_len:
        return s
    cut = s[:max_len].rsplit(" ", 1)[0].rstrip(",;:")
    return (cut or s[:max_len]) + "…"


def _caption_heading_from_context(ctx: str) -> str:
    """Use the nearest preceding markdown heading as a short caption."""
    lines = [ln.strip() for ln in (ctx or "").splitlines() if ln.strip()]
    for ln in reversed(lines[-18:]):
        if ln.startswith("#"):
            t = ln.lstrip("#").strip()
            if t:
                return _short_guidance_image_caption(t, 160)
    return ""


def _caption_from_tool_or_context(
    filename: str,
    diagram_caps: dict[str, str],
    md_alts: dict[str, str],
    context_before: str,
) -> str:
    cap = (diagram_caps.get(filename) or "").strip()
    if cap:
        return cap
    alt = (md_alts.get(filename) or "").strip()
    if len(alt) >= 6 and alt.lower() not in (
        "image",
        "diagram",
        "figure",
        "er diagram",
        "erd",
        "photo",
    ):
        return _short_guidance_image_caption(alt, 160)
    return _caption_heading_from_context(context_before)


_DIAGRAM_REQUEST_RE = re.compile(
    r"\b(draw|create|generate|design|sketch|construct|prepare|show|illustrate)\b.*\b(er\s*diagram|eerd?|entity\s*relationship|flowchart|diagram|schema|model)\b"
    r"|\b(er\s*diagram|eerd?|entity\s*relationship|flowchart|schema|(?:conceptual|logical|relational)\s+schema|data\s+model|entity\s*relationship\s+model)\b",
    re.IGNORECASE,
)

_CROW_FOOT_RE = re.compile(
    r"erDiagram|\|\|--|--\|\||\}o--|--o\{|\}\|--|--\|\{|\}\|\.{2}|\.{2}\|\{",
    re.IGNORECASE,
)


def _effective_audio_url(summary_doc: dict) -> Optional[str]:
    """Return audio URL for a summary: prefer GridFS endpoint when audio is stored there."""
    if not summary_doc:
        return None
    # If we have audio in GridFS, use the stream endpoint (works even if static file is missing)
    if summary_doc.get("audio_file_id"):
        return f"/protected/summaries/{summary_doc['_id']}/audio"
    return summary_doc.get("audio_url")


def extract_and_replace_images(
    content: str,
    base_url: str = "/api/images/",
    topic: Optional[str] = None,
    generate_explanations: bool = True,
    context_text: Optional[str] = None,
    diagram_registry: Optional[list[tuple[str, str]]] = None,
) -> tuple[str, list[str]]:
    """
    Extract image references from markdown and replace with proper image tags.
    Replaces each reference with a <figure> containing only an <img> (no captions).
    
    Args:
        content: Markdown content with [IMAGE:...] references
        base_url: Base URL for image paths
        topic: Unused (kept for API compatibility)
        generate_explanations: Ignored; captions are not embedded in HTML output
        context_text: Unused (kept for API compatibility)
        diagram_registry: Optional list of (filename, description) from this guidance run's
            ER tool calls, used to map hallucinated image names to the correct PNG.

    Returns:
        Tuple of (cleaned_content with inline images, list_of_image_paths)
    """
    if not content:
        return content, []

    guidance_diagram_registry: list[tuple[str, str]] = (
        list(diagram_registry) if diagram_registry else []
    )
    diagram_captions: dict[str, str] = {}
    for fn, desc in guidance_diagram_registry:
        if fn.startswith("guidance_er_diagram_") or fn.startswith(
            ("guidance_flowchart_", "guidance_general_")
        ):
            diagram_captions[fn] = _short_guidance_image_caption(desc, 200)

    preserved_markdown_alts: dict[str, str] = {}

    image_paths = []

    def _render_figure(
        encoded_name: str,
        display_name: str,
        caption: Optional[str] = None,
        *,
        hide_on_error: bool = False,
    ) -> str:
        extra = ' onerror="this.style.display=\'none\'"' if hide_on_error else ""
        alt_attr = html.escape(display_name, quote=True)
        cap = (caption or "").strip()
        figcap = ""
        if cap:
            figcap = f'\n<figcaption class="markdown-figcaption">{html.escape(cap)}</figcaption>'
        return (
            f'<figure>\n<img src="{base_url}{encoded_name}" alt="{alt_attr}" '
            f'class="markdown-image"{extra} />{figcap}\n</figure>'
        )

    # Normalize content: Handle [IMAGE:...], ![alt](IMAGE:...), and ![alt](filename.png) formats
    # Also handle cases where image names are split across lines
    def normalize_image_refs(text):
        # First, handle markdown image syntax: ![alt](IMAGE:filename) - handles multiline
        def fix_markdown_image(match):
            alt_text = (match.group(1) or "").strip()
            img_content = match.group(2)
            # Remove newlines and normalize whitespace
            img_content = re.sub(r'\s+', '', img_content)
            if img_content and len(alt_text) >= 4:
                preserved_markdown_alts[img_content] = alt_text[:500]
            return f'[IMAGE:{img_content}]'
        
        # Replace ![alt](IMAGE:filename) with [IMAGE:filename] - handles multiline alt/text
        # Pattern matches: ![anything](IMAGE:anything) even if split across lines
        # Use non-greedy matching and DOTALL to handle multiline content
        text = re.sub(
            r'!\[([^\]]*?)\]\(\s*IMAGE:\s*([^\)]+?)\s*\)',
            fix_markdown_image,
            text,
            flags=re.DOTALL | re.MULTILINE
        )
        
        # Also handle case where IMAGE: might be lowercase: ![alt](image:filename)
        text = re.sub(
            r'!\[([^\]]*?)\]\(\s*image:\s*([^\)]+?)\s*\)',
            fix_markdown_image,
            text,
            flags=re.DOTALL | re.MULTILINE | re.IGNORECASE
        )
        
        # CRITICAL: Handle plain markdown image syntax: ![alt](filename.png) and ![alt](https://.../filename.png)
        # CrewAI/LLM may output either local filenames or full URLs; we need [IMAGE:filename] for lookup.
        def fix_plain_markdown_image(match):
            alt_text = match.group(1) if match.group(1) else ""
            img_content = match.group(2)
            # Remove newlines and normalize whitespace (URLs can be split across lines)
            img_content = re.sub(r'\s+', '', img_content)
            
            # Skip if it already has IMAGE: prefix (should have been processed already, but double-check)
            if 'IMAGE:' in img_content.upper():
                return match.group(0)
            
            img_content_lower = img_content.lower()
            filename_for_ref = None

            # Case 1: Full URL (http/https) – extract filename from path for local lookup
            if img_content_lower.startswith(('http://', 'https://', '//')):
                try:
                    parsed = urlparse(img_content)
                    path = unquote(parsed.path)
                    if path and path != '/':
                        filename_for_ref = path.rstrip('/').split('/')[-1]
                except Exception:
                    filename_for_ref = None
                if filename_for_ref and re.search(r'\.(png|jpg|jpeg|gif|webp)$', filename_for_ref, re.IGNORECASE):
                    logger.info(f"Converting URL image to [IMAGE:...]: .../{filename_for_ref[:50]}...")
                    return f'[IMAGE:{filename_for_ref}]'
                return match.group(0)

            # Case 2: Local filename (has image extension, not a URL)
            if re.search(r'\.(png|jpg|jpeg|gif|webp)$', img_content, re.IGNORECASE) and not img_content.startswith(
                "/"
            ):
                logger.info(f"Converting plain markdown image to [IMAGE:...]: {img_content[:50]}...")
                if len(alt_text) >= 4:
                    preserved_markdown_alts[img_content] = alt_text[:500]
                return f'[IMAGE:{img_content}]'

            # Case 3: App-relative paths like /api/images/x.png or /guidance/api/images/x.png
            if re.search(r'\.(png|jpg|jpeg|gif|webp)$', img_content, re.IGNORECASE) and img_content.startswith(
                "/"
            ):
                path = unquote(img_content.split("?", 1)[0].strip())
                low = path.lower()
                for prefix in ("/guidance/api/images/", "/api/images/"):
                    if low.startswith(prefix):
                        fname = path[len(prefix) :].lstrip("/")
                        if fname and re.search(r"\.(png|jpg|jpeg|gif|webp)$", fname, re.IGNORECASE):
                            logger.info(f"Converting path markdown image to [IMAGE:...]: {fname[:80]}...")
                            if len(alt_text) >= 4:
                                preserved_markdown_alts[fname] = alt_text[:500]
                            return f'[IMAGE:{fname}]'
                        break
            return match.group(0)
        
        # Match ALL markdown images first, then filter in the function
        # This handles multiline cases better than trying to exclude URLs in the regex
        # Note: Images with IMAGE: prefix should already be converted above, but we check anyway
        text = re.sub(
            r'!\[([^\]]*?)\]\(\s*([^\)]+?)\s*\)',
            fix_plain_markdown_image,
            text,
            flags=re.DOTALL | re.MULTILINE
        )
        
        # Then normalize [IMAGE:...] patterns (remove newlines/whitespace inside)
        # This handles cases where [IMAGE:filename] is split across lines
        def fix_ref(match):
            img_content = match.group(1)
            # Remove ALL whitespace including newlines, tabs, spaces
            img_content = re.sub(r'\s+', '', img_content)
            logger.debug(f"Normalized image reference: {img_content[:80]}...")
            return f'[IMAGE:{img_content}]'
        # Use DOTALL to match across newlines, and make it non-greedy
        text = re.sub(r'\[IMAGE:([^\]]+?)\]', fix_ref, text, flags=re.DOTALL)
        
        return text
    
    # Log original content for debugging - check for both IMAGE: prefix and plain markdown
    original_image_refs_with_prefix = re.findall(r'!\[([^\]]*?)\]\(\s*IMAGE:\s*([^\)]+?)\s*\)', content, flags=re.DOTALL | re.MULTILINE)
    original_plain_image_refs = re.findall(r'!\[([^\]]*?)\]\(\s*([^\)]+?\.(?:png|jpg|jpeg|gif|webp))\s*\)', content, flags=re.DOTALL | re.MULTILINE | re.IGNORECASE)
    if original_image_refs_with_prefix:
        logger.info(f"Found {len(original_image_refs_with_prefix)} markdown image reference(s) with IMAGE: prefix before normalization")
    if original_plain_image_refs:
        logger.info(f"Found {len(original_plain_image_refs)} plain markdown image reference(s) (without IMAGE: prefix) before normalization: {[ref[1][:50] for ref in original_plain_image_refs[:3]]}")
    
    # Normalize image references first
    content = normalize_image_refs(content)

    # Pattern to match [IMAGE:...] (after normalization)
    image_pattern = r'\[IMAGE:([^\]]+)\]'
    
    # Log image references found in content after normalization
    image_matches = re.findall(image_pattern, content)
    if image_matches:
        logger.info(f"✅ Found {len(image_matches)} image reference(s) in content after normalization:")
        for i, img_match in enumerate(image_matches[:5], 1):
            logger.info(f"   {i}. [IMAGE:{img_match[:80]}...]")
    else:
        logger.warning("⚠ No [IMAGE:...] references found in content after normalization!")
        logger.debug(f"Content preview (first 500 chars): {content[:500]}")

    available_images = {}
    image_dirs = [GENERATED_IMAGE_OUTPUT_DIR, IMAGE_OUTPUT_DIR]
    found_any_dir = False
    for image_dir in image_dirs:
        if image_dir.exists():
            found_any_dir = True
            for img_file in image_dir.glob("*"):
                if img_file.is_file() and img_file.suffix.lower() in ['.jpeg', '.jpg', '.png', '.gif']:
                    available_images[img_file.name] = img_file.name
                    available_images[img_file.name.lower()] = img_file.name
    if found_any_dir:
        logger.info(f"Found {len(available_images)} available image(s) across generated/extracted image dirs")
        if image_matches and len(available_images) > 0:
            logger.info(f"Sample available images: {list(available_images.keys())[:5]}")
    else:
        logger.warning("No image directories found for generated/extracted images")

    # LLM often emits fake names (er_diagram_1.png, er-diagram-books-and-authors.png) while
    # the tool saves guidance_er_diagram_<hash>.png under generated_images.
    _diagram_remap_slot = [0]
    _hallucinated_er_cache: dict[str, str] = {}
    _remap_used_real_names: set[str] = set()

    def _is_server_generated_diagram_filename(name: str) -> bool:
        n = (name or "").lower()
        return bool(
            re.match(r"^guidance_er_diagram_[a-z0-9]+\.png$", n)
            or re.match(r"^guidance_(flowchart|general)_[a-z0-9_.-]+\.png$", n)
            or n.startswith("extracted_")
        )

    def _looks_like_hallucinated_er_image_name(name: str) -> bool:
        """True when basename is clearly not our saved tool output but looks ER-related."""
        raw = (name or "").strip()
        if not raw or _is_server_generated_diagram_filename(raw):
            return False
        stem = Path(raw).stem.lower()
        if re.match(r"^er[_\s-]*diagram(?:[_\s-].*)?$", stem):
            return True
        if re.match(r"^eerd?[_\s-]", stem) or re.match(r"^eer[_\s-]", stem):
            return True
        if "entity" in stem and "relationship" in stem.replace("-", "_"):
            return True
        return False

    def _should_remap_llm_invented_diagram_png(name: str) -> bool:
        """
        True for ER-ish hallucinations plus common placeholder / cardinality image names
        (e.g. 1_N_relationship.png, filename.png) that should map to real guidance_er_diagram_*.png.
        """
        raw = (name or "").strip()
        if not raw or not re.search(r"\.(png|jpe?g|gif|webp)$", raw, re.IGNORECASE):
            return False
        if _is_server_generated_diagram_filename(raw):
            return False
        if _looks_like_hallucinated_er_image_name(raw):
            return True
        stem = Path(raw).stem.lower()
        if stem in (
            "filename",
            "image",
            "diagram",
            "placeholder",
            "example",
            "your_diagram_here",
            "diagram_image",
        ):
            return True
        if stem.endswith("relationship") or stem.endswith("relationship_diagram"):
            return True
        # e.g. 1_1, 1_n, m_n, m_n_relationship
        base = re.sub(r"(_relationship|-relationship)(_diagram)?$", "", stem)
        if re.match(r"^[01mn]+_[01mn]+$", base):
            return True
        return False

    def _er_diagram_candidate_pool() -> list[Path]:
        candidates: list[Path] = []
        for image_dir in image_dirs:
            if image_dir.exists():
                candidates.extend(image_dir.glob("guidance_er_diagram_*.png"))
        return sorted(set(candidates), key=lambda p: p.resolve())

    def _slug_tokens_for_er_hallucination(raw: str) -> set[str]:
        stem = Path(raw).stem.lower()
        stem = re.sub(r"^er[_\s-]*diagram[_\s-]?", "", stem)
        stem = re.sub(r"^eerd?[_\s-]+", "", stem)
        parts = re.split(r"[_\s-]+", stem)
        stop = {
            "the", "and", "for", "with", "from", "into", "png", "img", "diagram",
            "entity", "relationship", "model", "schema", "conceptual", "logical",
        }
        tokens = {p for p in parts if len(p) >= 3 and p not in stop}
        # Cardinality placeholder filenames: 1_1_relationship, M_N_relationship, etc.
        rel_stem = Path(raw).stem.lower()
        rel_base = re.sub(r"(_relationship|-relationship)(_diagram)?$", "", rel_stem)
        if re.match(r"^[01mn]+_[01mn]+$", rel_base):
            for seg in re.findall(r"[01mn]+", rel_base):
                if seg:
                    tokens.add(seg)
            if "m" in rel_base and "n" in rel_base:
                tokens.update(("many-to-many", "many"))
            if rel_base == "1_1":
                tokens.add("one-to-one")
            elif re.match(r"^1_[mn]$", rel_base):
                tokens.add("one-to-many")
        return tokens

    def _ordered_er_candidates_for_remap(candidates: list[Path]) -> list[Path]:
        """
        Prefer diagrams from the current run: recent mtime window, oldest-first so slot order
        matches typical generation order (question 1 -> question 2).
        """
        if not candidates:
            return []
        now = time.time()
        recent_cutoff = now - 45 * 60  # 45 minutes
        recent = [p for p in candidates if p.stat().st_mtime >= recent_cutoff]
        pool = recent if len(recent) >= 1 else list(candidates)
        return sorted(pool, key=lambda p: p.stat().st_mtime)

    def _remap_hallucinated_er_diagram_from_registry(
        raw: str, context_before: str
    ) -> Optional[str]:
        """
        Prefer the PNG whose tool ``description`` matches the hallucinated slug / markdown context.
        Falls back to the next unused file in tool-call order.
        """
        if not guidance_diagram_registry:
            return None
        ctx_l = (context_before or "").lower()
        slug_tokens = _slug_tokens_for_er_hallucination(raw)
        rows: list[tuple[str, str]] = []
        for fn, desc in guidance_diagram_registry:
            if not re.match(r"^guidance_er_diagram_", fn, re.IGNORECASE):
                continue
            if fn in available_images or (GENERATED_IMAGE_OUTPUT_DIR / fn).is_file():
                rows.append((fn, desc))
        if not rows:
            return None
        unused = [r for r in rows if r[0] not in _remap_used_real_names]
        pool_rows = unused if unused else list(rows)

        best_fn: Optional[str] = None
        best_score = -1
        best_idx = 10**9
        for idx, (fn, desc) in enumerate(pool_rows):
            dlow = (desc or "").lower()
            sc = 0
            for t in slug_tokens:
                if len(t) < 2 and t not in ("m", "n", "1", "0"):
                    continue
                if len(t) == 1 and t not in ("m", "n", "1", "0"):
                    continue
                if t in dlow:
                    sc += 5
                if t in ctx_l:
                    sc += 2
            compact_ctx = re.sub(r"\s+", "", ctx_l)
            compact_desc = re.sub(r"\s+", "", dlow)
            for pat in ("1:1", "1:n", "n:1", "m:n", "n:m", "one-to-one", "one-to-many", "many-to-many"):
                if pat in ctx_l or pat in compact_ctx:
                    if pat in dlow or pat in compact_desc:
                        sc += 4
            if not slug_tokens:
                for w in set(re.findall(r"[a-z]{4,}", dlow)[:60]):
                    if len(w) < 4:
                        continue
                    if w in ctx_l:
                        sc += 1
            if sc > best_score or (sc == best_score and idx < best_idx):
                best_score = sc
                best_fn = fn
                best_idx = idx

        if not best_fn:
            return None
        if best_score <= 0:
            best_fn = pool_rows[0][0]
            logger.info("Registry ER remap (order): '%s' -> '%s'", raw, best_fn)
        else:
            logger.info(
                "Registry ER remap (scored): '%s' -> '%s' score=%s",
                raw,
                best_fn,
                best_score,
            )
        return best_fn

    def _remap_hallucinated_er_diagram(
        img_name: str, *, context_before: str = ""
    ) -> Optional[str]:
        """Map invented ER-ish filenames to real guidance_er_diagram_<hash>.png on disk."""
        raw = (img_name or "").strip()
        if not raw:
            return None
        if raw in _hallucinated_er_cache:
            return _hallucinated_er_cache[raw]
        if not _should_remap_llm_invented_diagram_png(raw):
            return None
        reg_name = _remap_hallucinated_er_diagram_from_registry(raw, context_before)
        if reg_name:
            _remap_used_real_names.add(reg_name)
            _hallucinated_er_cache[raw] = reg_name
            return reg_name
        candidates = _er_diagram_candidate_pool()
        if not candidates:
            return None
        ordered = _ordered_er_candidates_for_remap(candidates)
        ctx = (context_before or "").lower()
        slug_tokens = _slug_tokens_for_er_hallucination(raw)

        prefer_unused = [p for p in ordered if p.name not in _remap_used_real_names]
        pool = prefer_unused if prefer_unused else list(ordered)

        picked: Optional[Path] = None
        if slug_tokens and ctx:
            best_score = 0
            for p in pool:
                sc = 0
                for t in slug_tokens:
                    if len(t) < 2 and t not in ("m", "n", "1", "0"):
                        continue
                    if t in ctx:
                        sc += 2
                if sc > best_score:
                    best_score = sc
                    picked = p
            if picked is not None and best_score > 0:
                logger.info(
                    "Remapped ER diagram '%s' -> '%s' via slug/context overlap (score=%s)",
                    raw,
                    picked.name,
                    best_score,
                )

        if picked is None:
            slot = _diagram_remap_slot[0]
            _diagram_remap_slot[0] += 1
            picked = pool[min(slot, len(pool) - 1)]
            logger.info(f"Remapped hallucinated ER diagram name '{raw}' -> '{picked.name}' (slot {slot})")

        _remap_used_real_names.add(picked.name)
        _hallucinated_er_cache[raw] = picked.name
        return picked.name

    def replace_image(match):
        img_name = match.group(1).strip()
        logger.debug(f"Processing image reference: '{img_name[:80]}...'")
        ctx_start = max(0, match.start() - 1400)
        context_before = content[ctx_start : match.start()]

        actual_name = None
        # First try exact match
        if img_name in available_images:
            actual_name = available_images[img_name]
            logger.debug(f"Exact match found: {actual_name}")
        elif img_name.lower() in available_images:
            actual_name = available_images[img_name.lower()]
            logger.debug(f"Case-insensitive exact match found: {actual_name}")
        else:
            # Try partial matching for long filenames that might be split across lines
            img_name_lower = img_name.lower().replace('_', '').replace('-', '')
            logger.debug(f"Trying partial match for: {img_name_lower[:50]}...")
            for available_name in available_images.values():
                available_name_normalized = available_name.lower().replace('_', '').replace('-', '')
                # Check if the image name is contained in the available name or vice versa
                if (img_name_lower in available_name_normalized or 
                    available_name_normalized.startswith(img_name_lower) or
                    img_name_lower.startswith(available_name_normalized[:len(img_name_lower)])):
                    actual_name = available_name
                    logger.info(f"Partial match found: '{img_name[:50]}...' -> '{actual_name}'")
                    break

        if not actual_name:
            remapped = _remap_hallucinated_er_diagram(img_name, context_before=context_before)
            if remapped:
                actual_name = remapped
                available_images[actual_name] = actual_name
                available_images[actual_name.lower()] = actual_name
        
        if actual_name:
            if img_name != actual_name and img_name in preserved_markdown_alts:
                preserved_markdown_alts.setdefault(actual_name, preserved_markdown_alts[img_name])
            cap = _caption_from_tool_or_context(
                actual_name, diagram_captions, preserved_markdown_alts, context_before
            )
            if not cap and actual_name.lower().startswith("guidance_er_diagram_"):
                cap = "Conceptual ER diagram for this assignment section."
            elif not cap and actual_name.lower().startswith(
                ("guidance_flowchart_", "guidance_general_")
            ):
                cap = "Diagram for this assignment section."
            elif not cap and actual_name.lower().startswith("extracted_"):
                cap = "Figure from course materials."
            image_paths.append(actual_name)
            encoded_name = quote(actual_name)
            logger.info(f"Matched image '{img_name[:50]}...' -> '{actual_name}', URL: {base_url}{encoded_name}")
            return _render_figure(encoded_name, actual_name, cap or None)

        logger.error(f"❌ Image '{img_name[:50]}...' NOT FOUND in available images!")
        logger.error(f"   Searched for: {img_name}")
        logger.error(f"   Available images ({len(available_images)}): {list(available_images.keys())[:10]}")
        logger.warning("   Attempting to auto-generate missing diagram image")

        # Try generating a replacement diagram image when filename implies ER/schema/diagram.
        if re.search(r"(er|eer|entity|relationship|schema|diagram|weak\s*entity)", img_name, re.IGNORECASE):
            try:
                from app.ca_guidance.tools.diagram_image_tool import generate_assignment_diagram

                tool_out = generate_assignment_diagram.run(
                    diagram_type="er_diagram",
                    description=f"Create conceptual ER diagram for: {img_name}",
                )
                new_refs = re.findall(r"\[IMAGE:([^\]]+)\]", tool_out or "", flags=re.IGNORECASE)
                if new_refs:
                    new_name = new_refs[0].strip()
                    if new_name:
                        available_images[new_name] = new_name
                        available_images[new_name.lower()] = new_name
                        image_paths.append(new_name)
                        encoded_name = quote(new_name)
                        acap = _caption_from_tool_or_context(
                            new_name, diagram_captions, preserved_markdown_alts, context_before
                        ) or "Conceptual ER diagram generated for this section."
                        return _render_figure(encoded_name, new_name, acap)
            except Exception as e:
                logger.warning(f"   Auto-generation for missing image failed: {e}")

        logger.warning("   Falling back to placeholder HTML - image may not display correctly")
        encoded_name = quote(img_name)
        return _render_figure(
            encoded_name,
            img_name,
            "Image could not be loaded; see the written explanation nearby.",
            hide_on_error=True,
        )

    cleaned_content = re.sub(image_pattern, replace_image, content)

    # Raw HTML <img src="/api/images/er_diagram_1.png"> (no [IMAGE:...]) — same hallucination remap
    def _fix_html_img_er_src(m: re.Match) -> str:
        pre, q, fname = m.group(1), m.group(2), m.group(3)
        fname_dec = unquote(fname)
        ctx_start = max(0, m.start() - 1400)
        context_before = m.string[ctx_start : m.start()]
        new_name = _remap_hallucinated_er_diagram(fname_dec, context_before=context_before)
        if not new_name:
            return m.group(0)
        return f"<img{pre}src={q}{base_url}{quote(new_name)}{q}"

    cleaned_content = re.sub(
        r"<img([^>]*?)\s*src=([\"'])(?:(?:/guidance)?/api/images/)([^\"']+)\2",
        _fix_html_img_er_src,
        cleaned_content,
        flags=re.IGNORECASE,
    )

    final_image_paths = list(set(image_paths))
    logger.info(f"Image extraction complete: {len(final_image_paths)} image(s) processed: {final_image_paths[:3]}...")
    
    # Verify HTML figure tags are in the content
    figure_count = cleaned_content.count('<figure>')
    img_count = cleaned_content.count('<img')
    logger.info(
        f"📊 HTML verification: Found {figure_count} <figure> tags and {img_count} <img> tags in final content"
    )

    if figure_count > 0:
        import re as re_module

        figure_matches = re_module.findall(r"<figure>.*?</figure>", cleaned_content, flags=re_module.DOTALL)
        if figure_matches:
            logger.info(f"✅ Sample figure HTML (first 400 chars): {figure_matches[0][:400]}...")
        img_src_matches = re_module.findall(r'<img[^>]+src=["\']([^"\']+)["\']', cleaned_content)
        if img_src_matches:
            logger.info(f"✅ Found {len(img_src_matches)} img src attributes: {img_src_matches[:3]}")
            for src in img_src_matches:
                if not src.startswith("/api/images/"):
                    logger.warning(f"⚠ Image src missing /api/images/ prefix: {src}")
    elif len(image_matches) > 0:
        logger.error(
            f"❌ CRITICAL: {len(image_matches)} images were matched but NO figure tags were generated!"
        )
        logger.error(f"Content preview (first 1000 chars): {cleaned_content[:1000]}")
    
    return cleaned_content, final_image_paths


def clean_markdown_response(content: str) -> str:
    """
    Clean up markdown response by removing debug messages and tool call information.
    """
    if not content:
        return content

    lines = content.split('\n')
    cleaned_lines = []
    skip_next_empty = False

    for line in lines:
        if re.search(r'Running:\s*transfer_task_to_\w+', line):
            skip_next_empty = True
            continue

        if re.match(r'^[\s-]*Running:\s*$', line):
            skip_next_empty = True
            continue

        if 'expected_output=...' in line or 'task_description=...' in line or 'additional_information=...' in line:
            skip_next_empty = True
            continue

        if skip_next_empty and line.strip() == '':
            skip_next_empty = False
            continue

        skip_next_empty = False
        cleaned_lines.append(line)

    content = '\n'.join(cleaned_lines)

    # Strip multi-part LLM boilerplate ("Not found in this part") that leaks into user-facing reports
    def _is_chunk_placeholder_line(line: str) -> bool:
        raw = (line or "").strip()
        if not raw or len(raw) > 200:
            return False
        # Heading or list item: normalize
        t = re.sub(r"^#{1,6}\s*", "", raw)
        t = re.sub(r"^[-*]\s+", "", t)
        t = re.sub(r"^\*\*|\*\*$", "", t).strip()
        low = t.lower()
        stub_phrases = (
            "not found in this part",
            "not found in this portion",
            "not in this part",
            "no content in this part",
            "nothing in this part",
            "n/a for this part",
            "not applicable to this part",
            "not covered in this part",
            "see other part",
            "refer to other part",
        )
        return any(p in low for p in stub_phrases)

    content = "\n".join(ln for ln in content.split("\n") if not _is_chunk_placeholder_line(ln))

    # Remove legacy auto-generated diagram headings/metadata; keep actual image refs.
    content = re.sub(r'^\s*#{2,6}\s*Auto-generated Diagram[^\n]*\n?', '', content, flags=re.IGNORECASE | re.MULTILINE)
    content = re.sub(r'^\s*Source request:\s*[^\n]*\n?', '', content, flags=re.IGNORECASE | re.MULTILINE)
    content = re.sub(r'^\s*\*\*Diagram for this question:\*\*\s*\n?', '', content, flags=re.IGNORECASE | re.MULTILINE)
    content = re.sub(r'\n{3,}', '\n\n', content)
    return content.strip()


def _task_output_text(task_output) -> str:
    """Best-effort plain text from a CrewAI task output object."""
    if task_output is None:
        return ""
    raw = getattr(task_output, "raw", None)
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    content = getattr(task_output, "content", None)
    if content is not None and str(content).strip():
        return str(content).strip()
    return str(task_output).strip()


def _merge_guidance_crew_task_outputs(result) -> Optional[str]:
    """
    Build the guidance report from per-part tasks when the finalize task truncates.

    ``result.raw`` / last-task output is often the finalize step only; the model
    may summarize into a short paragraph despite instructions. When
    ``tasks_output`` is present, concatenate all guidance parts and append the
    scheduling message unless finalize clearly retained the full merged body.
    """
    tasks_output = getattr(result, "tasks_output", None)
    if not tasks_output or len(tasks_output) < 3:
        return None

    guidance_slice = tasks_output[:-2]
    schedule_out = _task_output_text(tasks_output[-2])
    finalize_out = _task_output_text(tasks_output[-1])

    parts_text = "\n\n".join(t for t in (_task_output_text(x) for x in guidance_slice) if t)
    if not parts_text:
        return finalize_out or None

    min_finalize = max(400, int(0.45 * len(parts_text)))
    finalize_ok = bool(
        finalize_out
        and len(finalize_out) >= min_finalize
        and len(finalize_out) >= int(0.82 * len(parts_text))
    )

    if finalize_ok:
        logger.info(
            "Guidance merge: using finalize output (len=%s, parts_len=%s)",
            len(finalize_out),
            len(parts_text),
        )
        return finalize_out

    logger.warning(
        "Guidance merge: finalize output looks truncated vs part tasks "
        "(finalize_len=%s, parts_len=%s); assembling from part outputs + schedule.",
        len(finalize_out or ""),
        len(parts_text),
    )
    merged = parts_text + "\n\n### Deadline / Calendar Confirmation\n\n"
    merged += schedule_out or "_(No scheduling details returned.)_"
    return merged


def _extract_diagram_requests(assignment_text: str, limit: int = 18) -> list[str]:
    """Extract candidate question snippets that appear to request a diagram."""
    text = (assignment_text or "").strip()
    if not text:
        return []
    chunks = re.split(r'[\n\r]+|(?<=[.?!])\s+', text)
    requests: list[str] = []
    seen = set()
    for chunk in chunks:
        c = chunk.strip()
        if not c or len(c) < 12:
            continue
        if _DIAGRAM_REQUEST_RE.search(c):
            key = c.lower()
            if key in seen:
                continue
            seen.add(key)
            requests.append(c[:600])
            if len(requests) >= limit:
                break
    return requests


def _infer_diagram_type(request_text: str) -> str:
    low = (request_text or "").lower()
    if "flowchart" in low or "flow chart" in low or "workflow" in low:
        return "flowchart"
    return "er_diagram"


def _er_rule_hints(request_text: str) -> list[str]:
    """Map question text to ER rule hints aligned with app/er schema concepts."""
    low = (request_text or "").lower()
    hints: list[str] = []
    if "isa" in low or "inheritance" in low or "specialization" in low or "generalization" in low:
        hints.append("Include ISA hierarchy: parent entity with child entities; indicate disjoint/overlap and total/partial if stated.")
    if "weak entity" in low or "identifying relationship" in low or "dependent" in low:
        hints.append("Include weak entity modeling: weak entity, identifying relationship, and strong owner entity.")
    if "aggregation" in low or "whole-part" in low or "part of" in low:
        hints.append(
            "Include aggregation: whole entity plus part entities; inner binary relationship(s) with attributes inside the aggregate."
        )
    if "ternary" in low or "three-way" in low:
        hints.append("Include ternary relationship structure with three participating entities.")
    if "cardinality" in low or "1:n" in low or "m:n" in low or "one-to-many" in low or "many-to-many" in low:
        hints.append("Ensure explicit cardinalities on each relationship edge.")
    if "participation" in low or "total participation" in low or "partial participation" in low:
        hints.append("Include participation constraints (total/partial) where specified.")
    if "composite attribute" in low or "multivalued" in low:
        hints.append("Model composite/multivalued attributes as separate attribute nodes connected to owner.")
    if not hints:
        hints.append(
            "Use conceptual Chen-style ER from the CA text: rectangles (entities), diamonds (relationships), "
            "ovals (attributes, PK underlined in output), cardinality on edges; multivalued and composite modeled explicitly."
        )
    return hints


_DOT_FENCE_RE = re.compile(
    r"```\s*(?:dot|graphviz|gv)\s*\n([\s\S]*?)```",
    re.IGNORECASE,
)


def _looks_like_er_graphviz_dot(body: str) -> bool:
    """True if fenced code looks like an ER-style Graphviz graph (not arbitrary dot)."""
    b = (body or "").strip().lower()
    if len(b) < 24:
        return False
    if not re.search(r"\bgraph\s+[a-zA-Z0-9_]+\s*\{", b):
        return False
    if "graph er" in b:
        return True
    if _CROW_FOOT_RE.search(b):
        return False
    markers = (
        "graph er",
        "shape=ellipse",
        "shape=oval",
        "shape=diamond",
        "shape=box",
        "shape=rectangle",
        "rankdir",
        "splines",
        "node [shape",
        "peripheries",
        "subgraph cluster",
        "--",
        "[label=",
    )
    hits = sum(1 for m in markers if m in b)
    return hits >= 2


def _swap_er_graphviz_fences_for_images(assignment_text: str, content: str) -> str:
    """
    Replace ```dot / ```graphviz blocks that look like ER diagrams with PNG diagram tool output.
    Prevents raw DOT from appearing in the UI when the model should have used the diagram tool.
    """
    if not content or "```" not in content:
        return content
    try:
        from app.ca_guidance.tools.diagram_image_tool import generate_assignment_diagram
    except Exception as e:
        logger.warning("Diagram tool unavailable for DOT fence swap: %s", e)
        return content

    def _replace_block(match) -> str:
        inner = (match.group(1) or "").strip()
        if not _looks_like_er_graphviz_dot(inner):
            return match.group(0)
        base = (assignment_text or "").strip()[:9000]
        desc_parts = [
            "Build a validated conceptual Chen-style ER diagram for this CA assignment context.",
            "Ignore informal node declarations; extract entities, attributes (PK, multivalued, composite), "
            "relationships, and cardinalities from the assignment and from any draft hints below.",
        ]
        if base:
            desc_parts.append("ASSIGNMENT EXCERPT:\n" + base)
        desc_parts.append(
            "DRAFT GRAPHVIZ FROM MODEL (hints only; do not copy invalid syntax):\n" + inner[:4500]
        )
        description = "\n\n".join(desc_parts)
        try:
            tool_out = generate_assignment_diagram.run(
                diagram_type="er_diagram",
                description=description,
            )
            refs = re.findall(r"\[IMAGE:[^\]]+\]", tool_out or "", flags=re.IGNORECASE)
            if refs:
                logger.info("Replaced ER Graphviz fence with %d diagram image ref(s)", len(refs))
                return "\n\n" + "\n".join(refs) + "\n\n"
        except Exception as ex:
            logger.warning("ER diagram generation from DOT fence failed: %s", ex)
        # Remove unreadable DOT; do not leave raw fence on screen.
        return (
            "\n\n> Conceptual ER diagram: draft Graphviz was replaced. "
            "If no image appears above, re-run guidance or ask explicitly for an ER diagram.\n\n"
        )

    return _DOT_FENCE_RE.sub(_replace_block, content)


def _strip_crow_foot_blocks(content: str) -> str:
    """
    Remove fenced code blocks that contain Crow's Foot notation so rendered output
    does not show disallowed notation; Graphviz image sections are appended separately.
    """
    if not content:
        return content

    def _replace_block(match):
        block = match.group(0)
        if _CROW_FOOT_RE.search(block):
            return "\n\n> Crow's Foot text diagram removed. Conceptual ER image generated instead.\n\n"
        return block

    return re.sub(r"```[\s\S]*?```", _replace_block, content)


def _token_set(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", (text or "").lower())
    stop = {
        "the", "and", "for", "with", "that", "this", "from", "into", "your", "their",
        "question", "diagram", "draw", "create", "generate", "design", "schema", "erd",
        "eer", "entity", "relationship",
    }
    return {w for w in words if w not in stop}


def _find_best_insertion_line(content_lines: list[str], request_text: str) -> int | None:
    req_tokens = _token_set(request_text)
    if not req_tokens:
        return None

    best_idx = None
    best_score = 0.0
    for idx, line in enumerate(content_lines):
        line_tokens = _token_set(line)
        if not line_tokens:
            continue
        inter = len(req_tokens & line_tokens)
        if inter == 0:
            continue
        union = len(req_tokens | line_tokens)
        score = inter / union if union else 0.0
        # Prefer heading/question-like lines when score ties.
        if re.match(r"^\s{0,3}(#+\s+|Q\d+[:.)]|Question\s+\d+)", line, re.IGNORECASE):
            score += 0.08
        if score > best_score:
            best_score = score
            best_idx = idx

    # Require a minimal relevance threshold.
    if best_score < 0.08:
        return None
    return best_idx


def _has_image_near_line(content_lines: list[str], idx: int, window: int = 12) -> bool:
    start = max(0, idx)
    end = min(len(content_lines), idx + window + 1)
    snippet = "\n".join(content_lines[start:end])
    return bool(re.search(r"\[IMAGE:[^\]]+\]|<img\s+[^>]*src=", snippet, flags=re.IGNORECASE))


def _ensure_guidance_diagrams(
    assignment_text: str,
    cleaned_content: str,
) -> str:
    """
    Safety net: if assignment asks for diagrams but guidance output has no [IMAGE:...],
    invoke diagram generation tool directly and append generated image refs.
    """
    if not cleaned_content:
        return cleaned_content
    cleaned_content = _strip_crow_foot_blocks(cleaned_content)

    requests = _extract_diagram_requests(assignment_text)
    if not requests:
        return cleaned_content

    try:
        from app.ca_guidance.tools.diagram_image_tool import generate_assignment_diagram
    except Exception as e:
        logger.warning(f"Could not import diagram generation tool for fallback: {e}")
        return cleaned_content

    content_lines = cleaned_content.splitlines()
    inserts_made = 0

    for idx, req in enumerate(requests, start=1):
        anchor_idx = _find_best_insertion_line(content_lines, req)
        if anchor_idx is None:
            # Only insert when we can confidently map to a relevant question line.
            continue
        if _has_image_near_line(content_lines, anchor_idx):
            # Already has an image near the relevant question.
            continue

        diagram_type = _infer_diagram_type(req)
        try:
            hints = _er_rule_hints(req) if diagram_type == "er_diagram" else []
            description = req
            if hints:
                description = req + "\n\nER RULE HINTS:\n- " + "\n- ".join(hints)
            tool_output = generate_assignment_diagram.run(
                diagram_type=diagram_type,
                description=description,
            )
            image_refs = re.findall(r"\[IMAGE:[^\]]+\]", tool_output or "", flags=re.IGNORECASE)
            if not image_refs:
                continue
            # Place strictly under best-matching question line.
            insertion_block = ["", *image_refs, ""]
            content_lines[anchor_idx + 1:anchor_idx + 1] = insertion_block
            inserts_made += 1
        except Exception as e:
            logger.warning(f"Fallback diagram generation failed for request '{req[:80]}...': {e}")

    new_content = "\n".join(content_lines).rstrip()
    if inserts_made:
        logger.info(f"Placed {inserts_made} diagram(s) under matched questions")
    return new_content


router = APIRouter(prefix="/protected", tags=["protected"])


@router.post("/run-guidance")
async def run_guidance(
    user: UserInfo = Depends(get_current_user),
    file: UploadFile = File(...)
):
    logger.info("=== Starting guidance process ===")

    logger.info("Step 1: Extracting text from PDF")
    try:
        pdf_bytes = await file.read()
        text = ""
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        logger.info(f"Extracted {len(text)} characters from PDF")

        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not extract any text from the uploaded PDF."
            )
    except Exception as e:
        logger.error(f"Error extracting PDF text: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process PDF file: {e}"
        )

    logger.info("Step 2: Creating and running CrewAI crew")
    try:
        from app.ca_guidance.tools.guidance_diagram_registry import (
            begin_guidance_diagram_registry,
            end_guidance_diagram_registry,
            get_guidance_diagram_registry,
        )

        begin_guidance_diagram_registry()
        try:
            crew = create_guidance_crew(
                assignment_text=text,
                access_token=user.access_token
            )

            logger.info("Step 3: Executing crew tasks")
            result = crew.kickoff()

            logger.info("Step 4: Extracting markdown from crew result")
            report_content = _merge_guidance_crew_task_outputs(result)

            if not report_content:
                if hasattr(result, 'raw'):
                    report_content = result.raw
                elif hasattr(result, 'content'):
                    report_content = result.content
                elif hasattr(result, 'tasks_output'):
                    if result.tasks_output:
                        last_task_output = result.tasks_output[-1]
                        report_content = (
                            last_task_output.raw
                            if hasattr(last_task_output, 'raw')
                            else str(last_task_output)
                        )
                elif isinstance(result, str):
                    report_content = result
                else:
                    report_content = str(result)

            if not report_content:
                logger.error("Failed to extract markdown from crew result")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to extract markdown report from crew result"
                )

            report_str = str(report_content)
            cleaned_content = clean_markdown_response(report_str)
            cleaned_content = _swap_er_graphviz_fences_for_images(text, cleaned_content)
            cleaned_content = _ensure_guidance_diagrams(
                assignment_text=text,
                cleaned_content=cleaned_content,
            )

            base_url = "/api/images/"
            diagram_registry = get_guidance_diagram_registry()
            if diagram_registry:
                logger.info(
                    "Guidance diagram registry: %s ER file(s) for image remapping",
                    len(diagram_registry),
                )
            # For guidance, explanations are optional (set to False by default)
            final_content, image_paths = extract_and_replace_images(
                cleaned_content,
                base_url=base_url,
                topic=None,  # Guidance doesn't have a specific topic
                generate_explanations=False,  # Disable for guidance to keep it focused
                context_text=None,
                diagram_registry=diagram_registry,
            )

            logger.info(f"Successfully extracted markdown (length: {len(final_content)})")
            logger.info(f"Found {len(image_paths)} image(s) in response")

            # Store base guidance for reinforcement flow (same style as summarization)
            try:
                from app.services.guidance_reinforcement_service import GuidanceReinforcementService
                svc = GuidanceReinforcementService()
                guidance_id = svc.store_base_guidance(
                    report_text=final_content,
                    images=image_paths,
                    user_email=user.email,
                )
                logger.info(f"Stored base guidance (id: {guidance_id})")
            except Exception as store_err:
                logger.warning(f"Failed to store base guidance for reinforcement: {store_err}")
                guidance_id = None

            logger.info("=== Guidance process completed ===")

            return {
                "report": final_content,
                "images": image_paths,
                "guidance_id": guidance_id,
            }
        finally:
            end_guidance_diagram_registry()

    except Exception as e:
        logger.error(f"Error running guidance manager: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to run guidance: {e}"
        )


@router.post("/guidance/download-pdf")
async def download_guidance_pdf(
    request: GuidancePdfRequest,
    user: UserInfo = Depends(get_current_user),
):
    report_content = (request.report_content or "").strip()
    if not report_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Guidance content is required to generate a PDF.",
        )

    try:
        from app.services.guidance_pdf_service import build_guidance_pdf, sanitize_download_filename

        pdf_bytes = build_guidance_pdf(
            report_content=report_content,
            image_names=request.images or [],
            title=(request.title or "CA Guidance Report").strip() or "CA Guidance Report",
        )
        filename = sanitize_download_filename(request.file_name)

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )
    except Exception as e:
        logger.error(f"Error generating guidance PDF for {user.email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate guidance PDF: {e}",
        )


@router.post("/summarize")
async def summarize_topic(
    request: SummarizeRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Create a comprehensive summary of a topic from lecture materials.
    
    Behavior:
    - Checks for existing reinforced summary first (returns if found)
    - Otherwise checks for latest base summary (returns if found)
    - Otherwise generates new summary and stores it
    
    Returns:
        JSON response with summary, related images, audio_url, and summary_id
    """
    topic = request.topic.strip()
    force = request.force
    logger.info(f"=== Starting summarization for topic: {topic} (force={force}) ===")

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty."
        )

    try:
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        
        # Check for existing summary if not forcing regeneration
        if not force:
            existing_summary = service.get_latest_summary(topic, prefer_reinforced=True, user_email=user.email)
            
            if existing_summary:
                logger.info(f"Found existing {existing_summary['summary_type']} summary for topic '{topic}'")
                # Check if existing summary has figure tags (explanations)
                existing_content = existing_summary["summary_text"]
                has_figures = "<figure>" in existing_content if existing_content else False
                logger.info(f"Existing summary has figure tags: {has_figures}")
                return {
                    "summary": existing_content,
                    "images": existing_summary.get("images", []),
                    "topic": topic,
                    "audio_url": _effective_audio_url(existing_summary),
                    "summary_id": existing_summary["_id"],
                    "summary_type": existing_summary["summary_type"],
                    "created_at": existing_summary.get("created_at").isoformat() if existing_summary.get("created_at") else None,
                    "audio_duration_seconds": existing_summary.get("audio_duration_seconds"),
                    "from_cache": True
                }
        
        # Generate new summary
        logger.info("Step 1: Creating and running summarization crew")
        crew = create_summarization_crew(topic=topic)

        logger.info("Step 2: Executing summarization task")
        result = crew.kickoff()

        logger.info("Step 3: Extracting summary from crew result")
        summary_content = None

        if hasattr(result, 'raw'):
            summary_content = result.raw
        elif hasattr(result, 'content'):
            summary_content = result.content
        elif hasattr(result, 'tasks_output'):
            if result.tasks_output:
                last_task_output = result.tasks_output[-1]
                summary_content = last_task_output.raw if hasattr(last_task_output, 'raw') else str(last_task_output)
        elif isinstance(result, str):
            summary_content = result
        else:
            summary_content = str(result)

        if not summary_content:
            logger.error("Failed to extract summary from crew result")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract summary from crew result"
            )

        summary_str = str(summary_content)
        cleaned_content = clean_markdown_response(summary_str)
        
        # Log to check if image references are in the content
        if "[IMAGE:" in cleaned_content:
            logger.info(f"Found [IMAGE:...] references in cleaned summary content")
        else:
            logger.warning(f"No [IMAGE:...] references found in cleaned summary content. Content length: {len(cleaned_content)}")
            # Try to extract images from the tool result if available
            # (CrewAI might have the tool result with images)
            if hasattr(result, 'tasks_output') and result.tasks_output:
                for task_output in result.tasks_output:
                    if hasattr(task_output, 'raw'):
                        tool_output = str(task_output.raw)
                        if "[IMAGE:" in tool_output:
                            logger.info("Found [IMAGE:...] references in task output, appending to summary")
                            # Extract image references and append them
                            import re
                            image_refs = re.findall(r'\[IMAGE:([^\]]+)\]', tool_output)
                            if image_refs:
                                cleaned_content += "\n\n**Related Images:**\n" + "\n".join([f"[IMAGE:{ref}]" for ref in image_refs])
                                logger.info(f"Added {len(image_refs)} image reference(s) to summary")

        base_url = "/api/images/"
        # Extract context text for image explanations (first 1000 chars of summary)
        context_for_explanations = cleaned_content[:1000] if len(cleaned_content) > 1000 else cleaned_content
        # Check if image explanations are enabled (can be disabled via env var if network issues)
        generate_explanations = settings.ENABLE_IMAGE_EXPLANATIONS
        logger.info(f"Image explanations setting: ENABLE_IMAGE_EXPLANATIONS = {generate_explanations}")
        if not generate_explanations:
            logger.info("⚠ Image explanations DISABLED via ENABLE_IMAGE_EXPLANATIONS setting")
        else:
            logger.info("✓ Image explanations ENABLED - will generate explanations for images")
        final_content, image_paths = extract_and_replace_images(
            cleaned_content, 
            base_url=base_url,
            topic=topic,
            generate_explanations=generate_explanations,
            context_text=context_for_explanations
        )

        # ✅ Generate audio from cleaned content (optional; skipped if Piper not configured)
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(final_content)  # outputs/audio/xxx.wav or None
            if audio_path:
                audio_url = f"/audio/{Path(audio_path).name}"
                logger.info(f"✅ Audio generated: {audio_url}")
            else:
                logger.info("TTS skipped (Piper not configured)")
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)

        # Store base summary in MongoDB (only if doesn't exist, unless force=True)
        summary_id = service.store_base_summary(
            topic=topic,
            summary_text=final_content,
            images=image_paths,
            audio_url=audio_url,
            force=force,
            user_email=user.email,
        )
        
        # summary_id should always be returned (either existing ID or new/updated ID)
        if not summary_id:
            logger.error(f"Failed to store base summary for topic '{topic}'")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store summary"
            )

        logger.info(f"Successfully created and stored summary (length: {len(final_content)})")
        logger.info(f"Found {len(image_paths)} image(s) in summary")
        
        # Verify HTML is in the final content before storing
        figure_count = final_content.count('<figure>')
        logger.info(f"📊 Final content verification: {figure_count} <figure> tags")
        if figure_count == 0 and len(image_paths) > 0:
            logger.warning(f"⚠ WARNING: {len(image_paths)} images found but NO figure tags in final content!")
            logger.warning(f"Content preview (first 500 chars): {final_content[:500]}")
        
        logger.info("=== Summarization completed ===")

        # Persist audio blob + duration metadata (optional)
        from bson.objectid import ObjectId
        audio_duration_seconds = None
        if audio_path and audio_url and summary_id:
            attach = service.attach_audio_to_summary(
                summary_id=summary_id,
                topic=topic,
                summary_type="base",
                audio_path=audio_path,
                user_email=user.email,
            )
            audio_duration_seconds = attach.get("audio_duration_seconds")
            # Prefer GridFS URL so audio works even if static file is missing
            if attach.get("audio_file_id"):
                audio_url = f"/protected/summaries/{summary_id}/audio"
                service.summaries_collection.update_one(
                    {"_id": ObjectId(summary_id)},
                    {"$set": {"audio_url": audio_url}},
                )

        # Get the stored summary to get created_at (+ possibly duration)
        stored_summary = service.summaries_collection.find_one({"_id": ObjectId(summary_id)})
        effective_audio_url = _effective_audio_url(stored_summary) if stored_summary else audio_url

        return {
            "summary": final_content,
            "images": image_paths,
            "topic": topic,
            "audio_url": effective_audio_url,
            "summary_id": summary_id,
            "summary_type": "base",
            "created_at": stored_summary.get("created_at").isoformat() if stored_summary and stored_summary.get("created_at") else None,
            "audio_duration_seconds": stored_summary.get("audio_duration_seconds") if stored_summary else audio_duration_seconds,
            "from_cache": False
        }

    except HTTPException:
        raise
    except Exception as e:
        err_msg = str(e)
        if "space quota" in err_msg.lower() or "over your space quota" in err_msg.lower():
            raise HTTPException(
                status_code=507,  # Insufficient Storage
                detail="Database storage quota exceeded. Please free space in MongoDB Atlas or upgrade your plan, then try again."
            )
        logger.error(f"Error creating summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create summary: {e}"
        )


class CheckSummaryAccuracyRequest(BaseModel):
    topic: str
    summary_content: str


class CheckGuidanceAccuracyRequest(BaseModel):
    guidance_content: str
    assignment_topic: Optional[str] = None


class FlashcardRequest(BaseModel):
    topic: str
    force: bool = False  # If True, regenerate even if exists in DB (same as SummarizeRequest)


@router.post("/check-summary-accuracy")
async def check_summary_accuracy(
    request: CheckSummaryAccuracyRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Check the accuracy of a summary using ROUGE metrics.
    
    Returns:
        JSON response with ROUGE scores and accuracy assessment
    """
    logger.info(f"=== Checking summary accuracy for topic: {request.topic} ===")
    
    try:
        rag_chain = _get_rag_chain()
        
        if rag_chain is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="RAG system is not available. The vectorstore needs to be built first."
            )
        
        # Query for relevant context
        summary_query = f"Provide detailed information about {request.topic} from lecture materials"
        result = rag_chain.invoke({"question": summary_query})
        
        # Extract context and verify accuracy
        context_text = _extract_context_text(result)
        
        if not context_text:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No relevant context found in lecture materials for this topic."
            )
        
        accuracy_result = _verify_summary_accuracy(
            summary=request.summary_content,
            context_text=context_text,
            topic=request.topic
        )
        
        logger.info(f"Accuracy check completed. Overall F-measure: {accuracy_result.get('overall', {}).get('avg_fmeasure_pct', 0):.2f}%")
        
        return accuracy_result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking summary accuracy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check summary accuracy: {e}"
        )


@router.post("/check-guidance-accuracy")
async def check_guidance_accuracy(
    request: CheckGuidanceAccuracyRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Check the accuracy of CA guidance using ROUGE metrics.
    
    Returns:
        JSON response with ROUGE scores and accuracy assessment
    """
    logger.info("=== Checking guidance accuracy ===")
    
    try:
        accuracy_result = verify_guidance_accuracy(
            guidance_text=request.guidance_content,
            assignment_topic=request.assignment_topic or ""
        )
        
        logger.info(f"Accuracy check completed. Overall F-measure: {accuracy_result.get('overall', {}).get('avg_fmeasure_pct', 0):.2f}%")
        
        return accuracy_result
        
    except Exception as e:
        logger.error(f"Error checking guidance accuracy: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check guidance accuracy: {e}"
        )


@router.post("/generate-flashcards")
async def generate_flashcards(
    request: FlashcardRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Create or retrieve Bloom's Taxonomy-based flashcards for a given topic.

    Default (force=False): Returns this user's previously saved flashcards for the topic
    from the database—their most recently stored set for that topic. User-specific; always
    the latest version available for that topic.

    Force regenerate (force=True): Generates new flashcards for the topic, then the frontend
    saves them to the database under this user's profile for future access. New sets are
    stored and can be accessed whenever needed.

    Storage and viewability: All sets are stored per user (user_email). Whether pulled
    from DB or newly generated, the flashcards returned are recent and specific to the user.
    """
    topic = request.topic.strip()
    force = request.force
    logger.info(f"=== Starting flashcard get/generate for topic: {topic} (force={force}) ===")

    if not topic:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Topic is required and cannot be empty."
        )

    try:
        from app.core.config import settings as _settings
        # Check for existing flashcard set if not forcing regeneration (same pattern as summarize_topic)
        if not force:
            from pymongo import MongoClient
            import certifi

            client = MongoClient(_settings.MONGO_URI, tlsCAFile=certifi.where())
            db = client.ca_guidance
            flashcard_sets = db.flashcard_sets
            # Most recent saved set for this user and topic (case-insensitive topic match)
            topic_regex = re.compile(f"^{re.escape(topic)}$", re.IGNORECASE)
            flashcard_set = flashcard_sets.find_one(
                {"topic": topic_regex, "user_email": user.email},
                sort=[("created_at", -1)]
            )
            if flashcard_set:
                logger.info(f"Found saved flashcard set for topic '{topic}' (user-specific)")
                return {
                    "topic": flashcard_set["topic"],
                    "flashcards": flashcard_set["flashcards"],
                    "flashcard_set_id": str(flashcard_set["_id"]),
                    "from_saved": True,
                    "from_cache": True,  # Same key as summarization when returning stored
                }
            logger.info(f"No saved set for topic '{topic}', will generate")

        # Generate new flashcards
        from langchain_openai import ChatOpenAI
        from app.ca_guidance.agents.flashcard_agent import FlashcardAgent
        
        # Initialize LLM for flashcard generation
        # Use GPT model explicitly for flashcard generation
        model_name = "gpt-4o-mini"  # Use GPT model for flashcard generation
        llm = ChatOpenAI(
            model=model_name,
            api_key=_settings.OPENAI_API_KEY,
            temperature=0.3,  # Lower temperature for more consistent flashcard generation
        )
        
        # Create flashcard agent
        agent = FlashcardAgent(llm=llm)
        
        logger.info("Step 1: Generating flashcards using FlashcardAgent")
        result = agent.generate_flashcards(topic)
        
        logger.info(f"Successfully generated flashcards for topic: {topic}")
        logger.info("=== Flashcard generation completed ===")
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating flashcards: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate flashcards: {str(e)}"
        )


# ============ Flashcard Feedback Endpoints ============

@router.post("/flashcards/save")
async def save_flashcard_set(
    request: SaveFlashcardSetRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Save a generated flashcard set to the database under this user's profile.
    Stored sets are available for future access (default flow will pull them by topic).
    """
    logger.info(f"=== Saving flashcard set for topic: {request.topic} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        import uuid
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        # Add unique IDs to each flashcard if they don't have one
        flashcards_with_ids = {}
        for level, cards in request.flashcards.items():
            flashcards_with_ids[level] = []
            for card in cards:
                flashcards_with_ids[level].append({
                    "id": card.get("id") or str(uuid.uuid4()),
                    "question": card["question"],
                    "answer": card["answer"]
                })
        
        doc = {
            "topic": request.topic,
            "user_email": user.email,
            "flashcards": flashcards_with_ids,
            "version": 1,
            "created_at": datetime.utcnow(),
            "updated_at": None
        }
        
        result = flashcard_sets.insert_one(doc)
        logger.info(f"Flashcard set saved with ID: {result.inserted_id}")
        
        return {
            "flashcard_set_id": str(result.inserted_id),
            "topic": request.topic,
            "flashcards": flashcards_with_ids,
            "version": 1,
            "message": "Flashcard set saved successfully"
        }
        
    except Exception as e:
        logger.error(f"Error saving flashcard set: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save flashcard set: {str(e)}"
        )


@router.post("/flashcards/feedback")
async def submit_flashcard_feedback(
    request: FlashcardFeedbackRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Submit feedback for a specific flashcard."""
    logger.info(f"=== Submitting feedback for flashcard {request.flashcard_id} ===")
    
    try:
        from datetime import datetime
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_feedback = db.flashcard_feedback
        
        doc = {
            "flashcard_set_id": request.flashcard_set_id,
            "flashcard_id": request.flashcard_id,
            "bloom_level": request.bloom_level,
            "user_email": user.email,
            "rating": request.rating,
            "feedback_type": request.feedback_type,
            "comment": request.comment,
            "session_id": request.session_id,
            "created_at": datetime.utcnow(),
            "processed": False
        }
        
        result = flashcard_feedback.insert_one(doc)
        logger.info(f"Flashcard feedback stored (id: {result.inserted_id})")
        
        return {
            "feedback_id": str(result.inserted_id),
            "flashcard_set_id": request.flashcard_set_id,
            "flashcard_id": request.flashcard_id,
            "message": "Feedback submitted successfully"
        }
        
    except Exception as e:
        logger.error(f"Error storing flashcard feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {str(e)}"
        )


@router.post("/flashcards/improve")
async def improve_flashcard(
    request: FlashcardUpdateRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Improve a flashcard based on submitted feedback."""
    logger.info(f"=== Improving flashcard {request.flashcard_id} ===")
    
    try:
        from datetime import datetime
        from bson.objectid import ObjectId
        from langchain_openai import ChatOpenAI
        from app.core.config import settings
        from app.ca_guidance.agents.flashcard_improvement_agent import FlashcardImprovementAgent
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        flashcard_feedback = db.flashcard_feedback
        
        feedback_doc = flashcard_feedback.find_one({"_id": ObjectId(request.feedback_id)})
        if not feedback_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")
        
        flashcard_set = flashcard_sets.find_one({"_id": ObjectId(request.flashcard_set_id)})
        if not flashcard_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")
        
        bloom_level = request.bloom_level
        flashcard = None
        flashcard_index = -1
        
        if bloom_level in flashcard_set["flashcards"]:
            for i, card in enumerate(flashcard_set["flashcards"][bloom_level]):
                if card["id"] == request.flashcard_id:
                    flashcard = card
                    flashcard_index = i
                    break
        
        if not flashcard:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard not found")
        
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=settings.OPENAI_API_KEY, temperature=0.3)
        agent = FlashcardImprovementAgent(llm=llm)
        
        improved = agent.improve_flashcard(
            topic=flashcard_set["topic"],
            question=flashcard["question"],
            answer=flashcard["answer"],
            bloom_level=bloom_level,
            feedback_type=feedback_doc.get("feedback_type"),
            comment=feedback_doc.get("comment")
        )
        
        new_version = flashcard_set.get("version", 1) + 1
        
        flashcard_sets.update_one(
            {"_id": ObjectId(request.flashcard_set_id)},
            {
                "$set": {
                    f"flashcards.{bloom_level}.{flashcard_index}.question": improved["question"],
                    f"flashcards.{bloom_level}.{flashcard_index}.answer": improved["answer"],
                    "version": new_version,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        flashcard_feedback.update_one(
            {"_id": ObjectId(request.feedback_id)},
            {"$set": {"processed": True, "processed_at": datetime.utcnow()}}
        )
        
        logger.info(f"Flashcard improved successfully. New version: {new_version}")
        
        return {
            "flashcard_id": request.flashcard_id,
            "bloom_level": bloom_level,
            "original_question": flashcard["question"],
            "original_answer": flashcard["answer"],
            "updated_question": improved["question"],
            "updated_answer": improved["answer"],
            "improvement_notes": improved["improvement_notes"],
            "version": new_version,
            "message": "Flashcard improved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error improving flashcard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to improve flashcard: {str(e)}"
        )


@router.get("/flashcards/recent")
async def get_recent_flashcards(
    user: UserInfo = Depends(get_current_user)
):
    """Get the most recently created flashcard set for the current user."""
    logger.info("=== Getting recent flashcard set for user ===")
    try:
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi

        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets

        flashcard_set = flashcard_sets.find_one(
            {"user_email": user.email},
            sort=[("created_at", -1)]
        )
        if not flashcard_set:
            return {"found": False, "message": "No flashcards found for this user"}

        return {
            "found": True,
            "_id": str(flashcard_set["_id"]),
            "topic": flashcard_set["topic"],
            "flashcards": flashcard_set["flashcards"],
            "version": flashcard_set.get("version", 1),
            "created_at": flashcard_set["created_at"].isoformat() if flashcard_set.get("created_at") else None,
            "updated_at": flashcard_set["updated_at"].isoformat() if flashcard_set.get("updated_at") else None,
        }
    except Exception as e:
        logger.error(f"Error getting recent flashcards: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get recent flashcards: {str(e)}"
        )


@router.get("/flashcards/topic/{topic}")
async def get_flashcards_by_topic(
    topic: str,
    user: UserInfo = Depends(get_current_user)
):
    """Get the most recently saved flashcard set for this user and topic."""
    logger.info(f"=== Getting flashcards for topic: {topic} ===")
    
    try:
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        flashcard_set = flashcard_sets.find_one(
            {"topic": topic, "user_email": user.email},
            sort=[("created_at", -1)]
        )
        
        if not flashcard_set:
            return {"found": False, "message": "No flashcards found for this topic"}
        
        return {
            "found": True,
            "_id": str(flashcard_set["_id"]),
            "topic": flashcard_set["topic"],
            "flashcards": flashcard_set["flashcards"],
            "version": flashcard_set.get("version", 1),
            "created_at": flashcard_set["created_at"].isoformat() if flashcard_set.get("created_at") else None,
            "updated_at": flashcard_set["updated_at"].isoformat() if flashcard_set.get("updated_at") else None
        }
        
    except Exception as e:
        logger.error(f"Error getting flashcards by topic: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get flashcards: {str(e)}"
        )


@router.get("/flashcards/{flashcard_set_id}")
async def get_flashcard_set(
    flashcard_set_id: str,
    user: UserInfo = Depends(get_current_user)
):
    """Get a flashcard set by ID."""
    logger.info(f"=== Getting flashcard set {flashcard_set_id} ===")
    
    try:
        from bson.objectid import ObjectId
        from app.core.config import settings
        from pymongo import MongoClient
        import certifi
        
        client = MongoClient(settings.MONGO_URI, tlsCAFile=certifi.where())
        db = client.ca_guidance
        flashcard_sets = db.flashcard_sets
        
        flashcard_set = flashcard_sets.find_one({"_id": ObjectId(flashcard_set_id)})
        if not flashcard_set:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flashcard set not found")
        
        return {
            "_id": str(flashcard_set["_id"]),
            "topic": flashcard_set["topic"],
            "flashcards": flashcard_set["flashcards"],
            "version": flashcard_set.get("version", 1),
            "created_at": flashcard_set["created_at"].isoformat() if flashcard_set.get("created_at") else None,
            "updated_at": flashcard_set["updated_at"].isoformat() if flashcard_set.get("updated_at") else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flashcard set: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get flashcard set: {str(e)}"
        )


# ============ Summary Feedback Endpoints ============

@router.post("/summaries/feedback")
async def submit_summary_feedback(
    request: SummaryFeedbackRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Submit feedback for a summary.
    
    Returns:
        JSON response with feedback_id
    """
    logger.info(f"=== Submitting feedback for summary {request.summary_id} ===")
    
    try:
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        
        feedback_id = service.store_feedback(
            topic=request.topic,
            summary_id=request.summary_id,
            rating=request.rating,
            confused_concept=request.confused_concept,
            comment=request.comment,
            feedback_type=request.feedback_type,
            user_email=user.email,
            session_id=request.session_id,
        )
        
        logger.info(f"Feedback stored successfully (id: {feedback_id})")
        
        return {
            "feedback_id": feedback_id,
            "message": "Feedback submitted successfully"
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error storing feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to store feedback: {e}"
        )


@router.post("/summaries/reinforce")
async def reinforce_summary(
    request: ReinforceSummaryRequest,
    user: UserInfo = Depends(get_current_user)
):
    """
    Generate a reinforced summary based on feedback.
    
    Returns:
        JSON response with reinforced summary, images, audio_url, and summary_id
    """
    logger.info(f"=== Generating reinforced summary for topic: {request.topic} (force={request.force}) ===")
    
    try:
        from bson.objectid import ObjectId
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        
        # Check if reinforced summary exists and force=False
        if not request.force:
            existing_reinforced = service.get_latest_summary(request.topic, prefer_reinforced=True, user_email=user.email)
            if existing_reinforced and existing_reinforced.get("summary_type") == "reinforced":
                logger.info(f"Found existing reinforced summary for topic '{request.topic}'")
                return {
                    "summary": existing_reinforced["summary_text"],
                    "images": existing_reinforced.get("images", []),
                    "topic": request.topic,
                    "audio_url": _effective_audio_url(existing_reinforced),
                    "summary_id": existing_reinforced["_id"],
                    "summary_type": "reinforced",
                    "created_at": existing_reinforced.get("created_at").isoformat() if existing_reinforced.get("created_at") else None,
                    "audio_duration_seconds": existing_reinforced.get("audio_duration_seconds"),
                    "from_cache": True
                }
        
        # Get the base summary
        try:
            summary_obj_id = ObjectId(request.summary_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid summary_id format: {request.summary_id}"
            )
        
        base_summary_doc = service.summaries_collection.find_one({"_id": summary_obj_id})
        
        if not base_summary_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Summary with id {request.summary_id} not found"
            )
        
        base_summary_text = base_summary_doc["summary_text"]
        
        # Get feedback - prioritize feedback_id if provided, otherwise get latest for this summary
        feedback = {}
        feedback_id_to_store = None
        
        if request.feedback_id:
            try:
                feedback_obj_id = ObjectId(request.feedback_id)
                feedback_doc = service.feedback_collection.find_one({"_id": feedback_obj_id})
                if feedback_doc:
                    feedback = {
                        "rating": feedback_doc.get("rating", "not_helpful"),
                        "confused_concept": feedback_doc.get("confused_concept"),
                        "comment": feedback_doc.get("comment"),
                        "feedback_type": feedback_doc.get("feedback_type"),
                    }
                    feedback_id_to_store = str(feedback_obj_id)
                    logger.info(f"Using specific feedback_id: {feedback_id_to_store}")
            except Exception as e:
                logger.warning(f"Invalid feedback_id format: {request.feedback_id}, error: {e}")
        
        # If no feedback_id provided or invalid, get latest feedback for this summary
        if not feedback:
            latest_feedback = service.get_latest_feedback_for_summary(
                request.summary_id, user_email=user.email, session_id=request.session_id
            )
            if latest_feedback:
                feedback = {
                    "rating": latest_feedback.get("rating", "not_helpful"),
                    "confused_concept": latest_feedback.get("confused_concept"),
                    "comment": latest_feedback.get("comment"),
                    "feedback_type": latest_feedback.get("feedback_type"),
                }
                feedback_id_to_store = latest_feedback.get("_id")
                logger.info(f"Using latest feedback for summary: {feedback_id_to_store}")
        
        # Default feedback if none found
        if not feedback:
            feedback = {"rating": "not_helpful"}  # Default
            logger.warning("No feedback found, using default 'not_helpful'")
        
        # Generate reinforced summary
        logger.info("Generating reinforced summary using LLM...")
        reinforced_text = service.generate_reinforced_summary(
            topic=request.topic,
            base_summary_text=base_summary_text,
            feedback=feedback
        )
        
        # Generate audio for reinforced summary (optional; skipped if Piper not configured)
        audio_url = None
        audio_path = None
        try:
            audio_path = text_to_speech_wav(reinforced_text)
            if audio_path:
                audio_url = f"/audio/{Path(audio_path).name}"
                logger.info(f"✅ Audio generated for reinforced summary: {audio_url}")
            else:
                logger.info("TTS skipped (Piper not configured)")
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)
        
        # Extract images from base summary (reuse them)
        images = base_summary_doc.get("images", [])
        
        # Store reinforced summary (use feedback_id_to_store if we found one)
        reinforced_summary_id = service.store_reinforced_summary(
            topic=request.topic,
            summary_text=reinforced_text,
            base_summary_id=request.summary_id,
            feedback_id=feedback_id_to_store or request.feedback_id,
            images=images,
            audio_url=audio_url,
            user_email=user.email,
            session_id=request.session_id,
        )

        # Persist audio blob + duration metadata (optional)
        audio_duration_seconds = None
        if audio_path and audio_url and reinforced_summary_id:
            attach = service.attach_audio_to_summary(
                summary_id=reinforced_summary_id,
                topic=request.topic,
                summary_type="reinforced",
                audio_path=audio_path,
                user_email=user.email,
                session_id=request.session_id,
            )
            audio_duration_seconds = attach.get("audio_duration_seconds")
            if attach.get("audio_file_id"):
                audio_url = f"/protected/summaries/{reinforced_summary_id}/audio"
                service.summaries_collection.update_one(
                    {"_id": ObjectId(reinforced_summary_id)},
                    {"$set": {"audio_url": audio_url}},
                )
        
        logger.info(f"Reinforced summary generated and stored (id: {reinforced_summary_id})")
        
        # Get the stored reinforced summary to get created_at
        stored_reinforced = service.summaries_collection.find_one({"_id": ObjectId(reinforced_summary_id)})
        effective_audio_url = _effective_audio_url(stored_reinforced) if stored_reinforced else audio_url
        
        return {
            "summary": reinforced_text,
            "images": images,
            "topic": request.topic,
            "audio_url": effective_audio_url,
            "summary_id": reinforced_summary_id,
            "summary_type": "reinforced",
            "base_summary_id": request.summary_id,
            "feedback_id": request.feedback_id,
            "created_at": stored_reinforced.get("created_at").isoformat() if stored_reinforced and stored_reinforced.get("created_at") else None,
            "audio_duration_seconds": stored_reinforced.get("audio_duration_seconds") if stored_reinforced else audio_duration_seconds,
            "from_cache": False
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reinforced summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reinforced summary: {e}"
        )


@router.get("/summaries/{summary_id}/audio")
async def get_summary_audio(
    summary_id: str,
    user: UserInfo = Depends(get_current_user),
):
    """
    Stream summary audio from GridFS (WAV). Use this URL when summary has audio stored.
    """
    from bson.objectid import ObjectId
    from app.services.summary_reinforcement_service import SummaryReinforcementService

    try:
        oid = ObjectId(summary_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid summary_id")

    service = SummaryReinforcementService()
    doc = service.summaries_collection.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")

    # Optional: restrict to same user (or allow if no user_email on doc)
    if doc.get("user_email") and doc.get("user_email") != user.email:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Summary not found")

    audio_file_id = doc.get("audio_file_id")
    if not audio_file_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audio available for this summary")

    try:
        grid_out = service.audio_fs.get(ObjectId(audio_file_id) if isinstance(audio_file_id, str) else audio_file_id)
    except Exception as e:
        logger.warning(f"GridFS get failed for summary {summary_id}: {e}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")

    file_length = getattr(grid_out, "length", None)
    if file_length is None and hasattr(grid_out, "_file"):
        file_length = grid_out._file.get("length")

    def stream():
        chunk_size = 64 * 1024  # 64KB so first chunk arrives quickly for playback start
        try:
            while True:
                chunk = grid_out.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        finally:
            grid_out.close()

    headers = {
        "Content-Disposition": "inline; filename=summary_audio.wav",
        "Cache-Control": "private, max-age=300",
    }
    if file_length is not None:
        headers["Content-Length"] = str(file_length)
        headers["Accept-Ranges"] = "bytes"

    return StreamingResponse(
        stream(),
        media_type="audio/wav",
        headers=headers,
    )


@router.get("/summaries/topic/{topic}")
async def get_summaries_for_topic(
    topic: str,
    user: UserInfo = Depends(get_current_user)
):
    """
    Get all summaries (base and reinforced) for a topic.
    
    Returns:
        JSON response with both base and reinforced summaries
    """
    logger.info(f"=== Getting all summaries for topic: {topic} ===")
    
    try:
        from app.services.summary_reinforcement_service import SummaryReinforcementService
        
        service = SummaryReinforcementService()
        summaries = service.get_all_summaries_for_topic(topic, user_email=user.email)
        
        # Ensure audio_url is set from GridFS when we have audio_file_id
        base = summaries.get("base")
        reinforced = summaries.get("reinforced")
        if base:
            base["audio_url"] = _effective_audio_url(base)
        if reinforced:
            reinforced["audio_url"] = _effective_audio_url(reinforced)

        result = {
            "topic": topic,
            "base": base,
            "reinforced": reinforced
        }
        
        logger.info(f"Retrieved summaries for topic '{topic}'")
        return result
        
    except Exception as e:
        logger.error(f"Error getting summaries: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get summaries: {e}"
        )


# ============ Guidance Feedback and Reinforcement (same style as summarization) ============

@router.post("/guidance/feedback")
async def submit_guidance_feedback(
    request: GuidanceFeedbackRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Submit feedback for CA guidance. Required before reinforcement."""
    logger.info(f"=== Submitting feedback for guidance {request.guidance_id} ===")
    try:
        from app.services.guidance_reinforcement_service import GuidanceReinforcementService
        service = GuidanceReinforcementService()
        base = service.get_guidance(request.guidance_id, user_email=user.email)
        if not base or base.get("guidance_type") != "base":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base guidance not found or invalid.",
            )
        feedback_id = service.store_feedback(
            guidance_id=request.guidance_id,
            rating=request.rating,
            confused_concept=request.confused_concept,
            comment=request.comment,
            feedback_type=request.feedback_type,
            deadline_text=request.deadline_text,
            user_email=user.email,
            session_id=request.session_id,
        )
        return {"feedback_id": feedback_id, "message": "Feedback submitted successfully"}
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error storing guidance feedback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit guidance feedback: {e}",
        )


@router.post("/guidance/reinforce")
async def reinforce_guidance(
    request: ReinforceGuidanceRequest,
    user: UserInfo = Depends(get_current_user)
):
    """Generate reinforced CA guidance from the latest feedback (same flow as summarization)."""
    logger.info(f"=== Generating reinforced guidance for {request.guidance_id} (force={request.force}) ===")
    try:
        from bson.objectid import ObjectId
        from app.services.guidance_reinforcement_service import GuidanceReinforcementService
        service = GuidanceReinforcementService()
        base = service.get_guidance(request.guidance_id, user_email=user.email)
        if not base or base.get("guidance_type") != "base":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Base guidance not found.",
            )
        if not request.force:
            reinforced = service.get_reinforced_guidance(request.guidance_id, user_email=user.email)
            if reinforced:
                return {
                    "report": reinforced["report_text"],
                    "images": reinforced.get("images", []),
                    "guidance_id": request.guidance_id,
                    "reinforced_guidance_id": reinforced["_id"],
                    "guidance_type": "reinforced",
                    "from_cache": True,
                    "created_at": reinforced.get("created_at").isoformat() if reinforced.get("created_at") else None,
                }
        # Ensure we always work with the most recent version: reinforced (if any) or base.
        # All feedback (deadline, links, simplify, clarifications) is applied to this version
        # so the final document incorporates every change.
        latest_source = service.get_latest_guidance_for_reinforcement(request.guidance_id, user_email=user.email)
        if not latest_source:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Could not resolve latest guidance to reinforce.",
            )
        # Use the feedback that was just submitted (request.feedback_id from frontend) so the deadline is the one the user entered
        feedback = None
        feedback_id_to_store = request.feedback_id
        if request.feedback_id:
            try:
                fd = service.feedback_collection.find_one({"_id": ObjectId(request.feedback_id)})
                if fd:
                    feedback = {
                        "rating": fd.get("rating", "not_helpful"),
                        "confused_concept": fd.get("confused_concept"),
                        "comment": fd.get("comment"),
                        "feedback_type": fd.get("feedback_type"),
                        "deadline_text": fd.get("deadline_text"),
                    }
                    feedback_id_to_store = str(fd["_id"])
                    if fd.get("deadline_text"):
                        logger.info(f"Using deadline from submitted feedback: {fd.get('deadline_text')!r}")
            except Exception as e:
                logger.warning(f"Could not load feedback by id {request.feedback_id}: {e}")
        if not feedback:
            feedback_doc = service.get_latest_feedback_for_guidance(
                request.guidance_id, user_email=user.email, session_id=request.session_id
            )
            if feedback_doc:
                feedback = {
                    "rating": feedback_doc.get("rating", "not_helpful"),
                    "confused_concept": feedback_doc.get("confused_concept"),
                    "comment": feedback_doc.get("comment"),
                    "feedback_type": feedback_doc.get("feedback_type"),
                    "deadline_text": feedback_doc.get("deadline_text"),
                }
                feedback_id_to_store = feedback_doc.get("_id")
        if not feedback:
            feedback = {"rating": "not_helpful"}
        # For new_deadline_event: use ONLY the user-provided deadline from feedback. Do not use any deadline from the document.
        calendar_event_message = None
        user_provided_deadline = (feedback.get("deadline_text") or "").strip()
        access_token = getattr(user, "access_token", None) or (user.access_token if hasattr(user, "access_token") else None)
        if feedback.get("feedback_type") == "new_deadline_event" and user_provided_deadline:
            # Create calendar event with the user's new deadline only (never document-extracted deadline).
            if access_token:
                try:
                    from app.ca_guidance.tools.calendar_tool import create_calendar_event_with_token
                    calendar_event_message = create_calendar_event_with_token(
                        access_token=access_token,
                        title="CA Assignment: New deadline",
                        start_date=user_provided_deadline,
                        duration_hours=1,
                    )
                    logger.info(f"Calendar event (user deadline only): {calendar_event_message}")
                except Exception as cal_err:
                    logger.warning(f"Could not create calendar event: {cal_err}")
                    calendar_event_message = f"Calendar event could not be created: {cal_err}"
            else:
                calendar_event_message = (
                    "Calendar event was not created. Please sign in with Google to add the deadline to your calendar."
                )
                logger.info(f"No access token; calendar not created for deadline: {user_provided_deadline!r}")
        # Apply feedback to the latest version (never to a stale base)
        reinforced_text = service.generate_reinforced_guidance(
            base_report_text=latest_source["report_text"],
            feedback=feedback,
        )
        # 2) If user added a new deadline: remove any existing deadline/calendar section from the LLM output
        #    (it may contain an old date from the document), then append a single section with the user's date.
        if feedback.get("feedback_type") == "new_deadline_event" and user_provided_deadline:
            # Remove any ### heading that mentions Deadline or Calendar and its content up to the next ### or end
            def remove_deadline_sections(text: str) -> str:
                lines = text.split("\n")
                out = []
                skip_until_next_heading = False
                for line in lines:
                    if re.match(r"^#{2,6}\s+.*(?:deadline|calendar\s*confirmation|important\s*dates)", line, re.IGNORECASE):
                        skip_until_next_heading = True
                        continue
                    if skip_until_next_heading and re.match(r"^#{2,6}\s+", line):
                        skip_until_next_heading = False
                    if not skip_until_next_heading:
                        out.append(line)
                return "\n".join(out).rstrip()

            reinforced_text = remove_deadline_sections(reinforced_text)
            deadline_section = (
                "\n\n### Deadline / Calendar Confirmation\n\n"
                f"Your new deadline is **{user_provided_deadline}**. "
            )
            if calendar_event_message and "Successfully scheduled" in (calendar_event_message or ""):
                deadline_section += "The event has been added to your Google Calendar."
            elif calendar_event_message:
                deadline_section += "The calendar event could not be created automatically; please add this date to your calendar manually if needed."
            else:
                deadline_section += "Sign in with Google to add this deadline to your calendar."
            reinforced_text = reinforced_text.rstrip() + deadline_section
            logger.info(f"Deadline section set to user-provided date: {user_provided_deadline!r}")
        images = list(latest_source.get("images") or [])
        reinforced_text = clean_markdown_response(reinforced_text)
        reinforced_text = _swap_er_graphviz_fences_for_images("", reinforced_text)
        final_reinforced, extra_paths = extract_and_replace_images(
            reinforced_text,
            base_url="/api/images/",
            topic=None,
            generate_explanations=False,
            context_text=None,
        )
        reinforced_text = final_reinforced
        for p in extra_paths or []:
            if p and p not in images:
                images.append(p)
        reinforced_id = service.store_reinforced_guidance(
            base_guidance_id=request.guidance_id,
            report_text=reinforced_text,
            feedback_id=feedback_id_to_store,
            images=images,
            user_email=user.email,
            session_id=request.session_id,
        )
        stored = service.guidances_collection.find_one({"_id": ObjectId(reinforced_id)})
        response_data = {
            "report": reinforced_text,
            "images": images,
            "guidance_id": request.guidance_id,
            "reinforced_guidance_id": reinforced_id,
            "guidance_type": "reinforced",
            "from_cache": False,
            "created_at": stored.get("created_at").isoformat() if stored and stored.get("created_at") else None,
            "message": "Guidance updated with your feedback. You are viewing the latest version with all changes applied.",
        }
        # Always confirm calendar outcome in the response when user set a new deadline
        if feedback.get("feedback_type") == "new_deadline_event" and user_provided_deadline:
            response_data["calendar_event_message"] = calendar_event_message or (
                "Deadline was recorded; calendar event could not be created."
            )
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating reinforced guidance: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate reinforced guidance: {e}",
        )
