import html
import io
import logging
import re
import textwrap
from pathlib import Path
from typing import List, Optional, Tuple, Any
from urllib.parse import unquote, urlparse

import fitz

from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR, GENERATED_IMAGE_OUTPUT_DIR

logger = logging.getLogger(__name__)


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 48
MARGIN_Y = 52
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)
CONTENT_BOTTOM = PAGE_HEIGHT - MARGIN_Y


def _ensure_vertical_space(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    required_height: float,
    *,
    reason: str = "",
) -> tuple[fitz.Page, float]:
    """Create a new page if remaining vertical space is insufficient."""
    if y + required_height > CONTENT_BOTTOM:
        logger.debug(
            "PDF page break: reason=%s current_y=%s required=%s bottom=%s",
            reason or "auto-flow",
            round(y, 2),
            round(required_height, 2),
            CONTENT_BOTTOM,
        )
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = MARGIN_Y
    return page, y


def _draw_table(
    doc: fitz.Document,
    page: fitz.Page,
    y: float,
    columns: List[str],
    rows: List[List[str]],
) -> tuple[fitz.Page, float]:
    """
    Draw a simple bordered table with page-safe row flow.
    """
    cols = [str(c) for c in (columns or [])]
    if not cols:
        return page, y
    col_count = len(cols)
    table_width = CONTENT_WIDTH
    col_w = table_width / max(1, col_count)
    pad_x = 4
    pad_y = 3
    font_size = 9
    row_gap = 2

    def _row_height(values: List[str]) -> int:
        max_lines = 1
        # Rough wrap estimate per column width
        wrap_chars = max(8, int((col_w - (2 * pad_x)) / 5.5))
        for v in values:
            txt = str(v or "")
            chunks = textwrap.wrap(txt, width=wrap_chars, break_long_words=True, break_on_hyphens=False) or [""]
            max_lines = max(max_lines, len(chunks))
        return int((max_lines * (font_size + 2)) + (2 * pad_y))

    def _draw_row(values: List[str], is_header: bool = False) -> None:
        nonlocal page, y
        h = _row_height(values)
        page, y = _ensure_vertical_space(
            doc,
            page,
            y,
            h + row_gap,
            reason="table-row",
        )
        x = MARGIN_X
        for i, v in enumerate(values):
            rect = fitz.Rect(x, y, x + col_w, y + h)
            fill = (0.92, 0.95, 0.98) if is_header else None
            page.draw_rect(rect, color=(0.5, 0.5, 0.5), width=0.6, fill=fill)
            txt = str(v or "")
            wrap_chars = max(8, int((col_w - (2 * pad_x)) / 5.5))
            chunks = textwrap.wrap(txt, width=wrap_chars, break_long_words=True, break_on_hyphens=False) or [""]
            yy = y + pad_y + font_size
            for ch in chunks:
                page.insert_text(
                    fitz.Point(x + pad_x, yy),
                    ch,
                    fontsize=font_size,
                    fontname="helv",
                    color=(0.08, 0.12, 0.16),
                )
                yy += font_size + 2
            x += col_w
        y += h + row_gap

    _draw_row(cols, is_header=True)
    for r in rows[:25]:
        vals = [str(v) for v in (r or [])[:col_count]]
        if len(vals) < col_count:
            vals.extend([""] * (col_count - len(vals)))
        _draw_row(vals, is_header=False)
    return page, y


def sanitize_download_filename(file_name: Optional[str]) -> str:
    name = (file_name or "ca-guidance-report.pdf").strip() or "ca-guidance-report.pdf"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name or "ca-guidance-report.pdf"


def build_guidance_pdf(
    report_content: str,
    image_names: Optional[List[str]] = None,
    query_results: Optional[List[dict[str, Any]]] = None,
    title: str = "CA Guidance Report",
) -> bytes:
    logger.info(
        "build_guidance_pdf: title=%r report_chars=%s provided_images=%s",
        title,
        len(report_content or ""),
        len(image_names or []),
    )
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = MARGIN_Y

    page, y = _draw_text(doc, page, y, title, "title")
    y += 10

    unresolved_refs = _extract_unresolved_image_refs(report_content, image_names or [])
    if unresolved_refs:
        logger.warning(
            "build_guidance_pdf: unresolved image refs before render=%s sample=%s",
            len(unresolved_refs),
            unresolved_refs[:8],
        )

    segments = _segment_report_for_pdf(report_content)
    segment_text_count = sum(1 for kind, _ in segments if kind == "text")
    segment_image_count = sum(1 for kind, _ in segments if kind == "image")
    logger.info(
        "build_guidance_pdf: parsed_segments text=%s image=%s total=%s",
        segment_text_count,
        segment_image_count,
        len(segments),
    )
    seen_inline_names: set[str] = set()
    missing_inline_images: list[str] = []
    inline_embedded = 0
    rendered_line_count = 0

    for kind, payload in segments:
        if kind == "text":
            text_content = _html_to_text(payload)
            for line in text_content.splitlines():
                style = _style_for_line(line)
                text = _normalize_line(line, style)
                if not text and style != "blank":
                    continue
                page, y = _draw_text(doc, page, y, text, style)
                if text:
                    rendered_line_count += 1
        else:
            img_path = _resolve_single_image_path(payload)
            if img_path:
                seen_inline_names.add(Path(payload).name.lower())
                page, y = _draw_image(doc, page, y, img_path)
                inline_embedded += 1
            else:
                missing_inline_images.append(Path(payload).name)

    extra_images_resolved = _resolve_images(image_names or [])
    extra_embedded = 0

    for image_path in extra_images_resolved:
        key = Path(image_path).name.lower()
        if key in seen_inline_names:
            continue
        page, y = _draw_image(doc, page, y, image_path)
        extra_embedded += 1

    # Append SQL query results section when provided by backend guidance pipeline.
    if query_results:
        page, y = _ensure_vertical_space(doc, page, y, 80, reason="query-results-header")
        page, y = _draw_text(doc, page, y, "", "blank")
        page, y = _draw_text(doc, page, y, "SQL Dataset Query Results", "h2")
        logger.info("build_guidance_pdf: rendering query result tables count=%s", len(query_results))
        for idx, item in enumerate(query_results, start=1):
            q = str(item.get("query") or "").strip()
            expl = str(item.get("explanation") or "").strip()
            err = str(item.get("error") or "").strip()
            cols = [str(c) for c in (item.get("columns") or [])]
            rows = item.get("rows") or []
            page, y = _ensure_vertical_space(doc, page, y, 72, reason="query-block")
            page, y = _draw_text(doc, page, y, f"Query {idx}", "h3")
            if expl:
                page, y = _draw_text(doc, page, y, expl, "body")
            if q:
                page, y = _draw_text(doc, page, y, q, "body")
            if err:
                page, y = _draw_text(doc, page, y, f"Error: {err}", "body")
                continue
            if cols:
                logger.debug(
                    "PDF query table %s: columns=%s rows=%s",
                    idx,
                    len(cols),
                    len(rows),
                )
                page, y = _draw_table(
                    doc,
                    page,
                    y,
                    cols,
                    [list(map(str, row[: len(cols)])) for row in rows[:25]],
                )
            else:
                page, y = _draw_text(doc, page, y, "No tabular output returned.", "body")

    output = io.BytesIO()
    doc.save(output)
    page_count = doc.page_count
    doc.close()
    pdf_bytes = output.getvalue()
    if missing_inline_images:
        logger.warning(
            "build_guidance_pdf: unresolved inline images=%s sample=%s",
            len(missing_inline_images),
            missing_inline_images[:8],
        )
    logger.info(
        "build_guidance_pdf: inline_embedded=%s extra_embedded=%s extra_resolved=%s lines_rendered=%s pages=%s pdf_bytes=%s",
        inline_embedded,
        extra_embedded,
        len(extra_images_resolved),
        rendered_line_count,
        page_count,
        len(pdf_bytes),
    )
    if rendered_line_count < 12 and len(report_content or "") > 1800:
        logger.warning(
            "build_guidance_pdf: possible missing-content issue (report_chars=%s rendered_lines=%s)",
            len(report_content or ""),
            rendered_line_count,
        )
    return pdf_bytes


def _filename_from_image_reference(ref: str) -> str:
    """Resolve a local filename from markdown/HTML image URL or [IMAGE:...] fragment."""
    ref = (ref or "").strip()
    if not ref:
        return ""
    if ref.startswith(("http://", "https://")):
        path = urlparse(ref).path
    else:
        path = ref.split("?", 1)[0]
    path = unquote(path.replace("\\", "/"))
    lower = path.lower()
    for marker in ("/api/images/", "/images/"):
        if marker in lower:
            tail = path[lower.index(marker) + len(marker) :]
            return Path(tail.split("/")[-1]).name
    return Path(path).name


def _segment_report_for_pdf(report_content: str) -> List[Tuple[str, str]]:
    """Split report into ordered text and image segments (same order as on-screen content)."""
    content = report_content or ""
    content = re.sub(r"<figcaption>.*?</figcaption>", "", content, flags=re.IGNORECASE | re.DOTALL)
    pattern = re.compile(
        r'(?:<img\b[^>]*\bsrc=["\']([^"\']+)["\'][^>]*>)|'
        r'(?:!\[[^\]]*\]\(([^)]+)\))|'
        r'(?:\[IMAGE:\s*([^\]]+)\])',
        re.IGNORECASE,
    )
    out: List[Tuple[str, str]] = []
    pos = 0
    for m in pattern.finditer(content):
        if m.start() > pos:
            out.append(("text", content[pos : m.start()]))
        src = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        name = _filename_from_image_reference(src)
        if name:
            out.append(("image", name))
        pos = m.end()
    if pos < len(content):
        out.append(("text", content[pos:]))
    return out


def _extract_unresolved_image_refs(report_content: str, requested_images: List[str]) -> list[str]:
    """Gap-filling diagnostic: names referenced in content/request but not found on disk."""
    refs: list[str] = []
    requested = [Path(str(x)).name for x in (requested_images or []) if Path(str(x)).name]
    content = report_content or ""
    for m in re.finditer(r"\[IMAGE:\s*([^\]]+)\]", content, flags=re.IGNORECASE):
        name = _filename_from_image_reference(m.group(1) or "")
        if name:
            refs.append(name)
    for m in re.finditer(r"!\[[^\]]*\]\(([^)]+)\)", content, flags=re.IGNORECASE):
        name = _filename_from_image_reference(m.group(1) or "")
        if name and re.search(r"\.(png|jpg|jpeg|gif|webp)$", name, flags=re.IGNORECASE):
            refs.append(name)
    refs.extend(requested)
    unique_refs: list[str] = []
    seen = set()
    for r in refs:
        k = r.lower()
        if k in seen:
            continue
        seen.add(k)
        unique_refs.append(r)
    unresolved: list[str] = []
    for name in unique_refs:
        if _resolve_single_image_path(name) is None:
            unresolved.append(name)
    return unresolved


def _resolve_single_image_path(filename: str) -> Optional[Path]:
    name = Path(str(filename)).name
    if not name:
        return None
    for image_dir in (GENERATED_IMAGE_OUTPUT_DIR, IMAGE_OUTPUT_DIR):
        image_path = image_dir / name
        if image_path.is_file():
            return image_path
    logger.debug("PDF image resolve miss (inline): %s", name)
    return None


def _html_to_text(content: str) -> str:
    text = content or ""
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|figure|figcaption|li|h1|h2|h3|h4|h5|h6)\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return text


def _style_for_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return "blank"
    if stripped.startswith("# "):
        return "h1"
    if stripped.startswith("## "):
        return "h2"
    if stripped.startswith("### "):
        return "h3"
    if stripped.startswith("```"):
        return "blank"
    return "body"


def _normalize_line(line: str, style: str) -> str:
    stripped = line.strip()
    if style in {"h1", "h2", "h3"}:
        stripped = re.sub(r"^#{1,3}\s+", "", stripped)
    stripped = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", stripped)
    stripped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", stripped)
    stripped = re.sub(r"`([^`]+)`", r"\1", stripped)
    stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
    stripped = re.sub(r"\*([^*]+)\*", r"\1", stripped)
    return stripped


def _draw_text(doc: fitz.Document, page: fitz.Page, y: float, text: str, style: str):
    if style == "blank":
        if y > CONTENT_BOTTOM - 20:
            page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = MARGIN_Y
        return page, y + 10

    font_size, line_height, wrap_width = {
        "title": (20, 28, 46),
        "h1": (18, 24, 54),
        "h2": (15, 22, 62),
        "h3": (13, 20, 70),
        "body": (11, 18, 92),
    }[style]

    chunks = textwrap.wrap(text or "", width=wrap_width, replace_whitespace=False, drop_whitespace=False) or [""]
    for chunk in chunks:
        page, y = _ensure_vertical_space(doc, page, y, line_height, reason=f"text-{style}")
        page.insert_text(
            fitz.Point(MARGIN_X, y),
            chunk,
            fontsize=font_size,
            fontname="helv",
            color=(0.12, 0.18, 0.26),
        )
        y += line_height

    if style in {"title", "h1", "h2", "h3"}:
        y += 4
    return page, y


def _resolve_images(image_names: List[str]) -> List[Path]:
    resolved = []
    seen = set()
    for image_name in image_names:
        name = Path(str(image_name)).name
        if not name:
            continue
        found = False
        for image_dir in (GENERATED_IMAGE_OUTPUT_DIR, IMAGE_OUTPUT_DIR):
            image_path = image_dir / name
            key = str(image_path).lower()
            if image_path.exists() and key not in seen:
                seen.add(key)
                resolved.append(image_path)
                found = True
                break
        if not found:
            logger.debug("PDF image resolve miss (extra list): %s", name)
    return resolved


def _draw_image(doc: fitz.Document, page: fitz.Page, y: float, image_path: Path):
    pix = fitz.Pixmap(str(image_path))
    try:
        max_width = CONTENT_WIDTH
        max_height = 280
        scale = min(max_width / pix.width, max_height / pix.height, 1)
        width = pix.width * scale
        height = pix.height * scale

        # Keep visual separation from previous block to prevent perceived overlap.
        y += 4
        page, y = _ensure_vertical_space(doc, page, y, height + 24, reason="image")

        left = MARGIN_X + ((CONTENT_WIDTH - width) / 2)
        rect = fitz.Rect(left, y, left + width, y + height)
        page.insert_image(rect, filename=str(image_path))
        y += height + 16
        return page, y
    finally:
        pix = None
