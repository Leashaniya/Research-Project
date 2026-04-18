import html
import io
import re
import textwrap
from pathlib import Path
from typing import List, Optional

import fitz

from app.ca_guidance.rag.config.settings import IMAGE_OUTPUT_DIR, GENERATED_IMAGE_OUTPUT_DIR


PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN_X = 48
MARGIN_Y = 52
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN_X)
CONTENT_BOTTOM = PAGE_HEIGHT - MARGIN_Y


def sanitize_download_filename(file_name: Optional[str]) -> str:
    name = (file_name or "ca-guidance-report.pdf").strip() or "ca-guidance-report.pdf"
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return name or "ca-guidance-report.pdf"


def build_guidance_pdf(report_content: str, image_names: Optional[List[str]] = None, title: str = "CA Guidance Report") -> bytes:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
    y = MARGIN_Y

    page, y = _draw_text(doc, page, y, title, "title")
    y += 10

    text_content = _html_to_text(report_content)
    for line in text_content.splitlines():
        style = _style_for_line(line)
        text = _normalize_line(line, style)
        if not text and style != "blank":
            continue
        page, y = _draw_text(doc, page, y, text, style)

    for image_path in _resolve_images(image_names or []):
        page, y = _draw_image(doc, page, y, image_path)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue()


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
        if y > CONTENT_BOTTOM - line_height:
            page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
            y = MARGIN_Y
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
        for image_dir in (GENERATED_IMAGE_OUTPUT_DIR, IMAGE_OUTPUT_DIR):
            image_path = image_dir / name
            key = str(image_path).lower()
            if image_path.exists() and key not in seen:
                seen.add(key)
                resolved.append(image_path)
                break
    return resolved


def _draw_image(doc: fitz.Document, page: fitz.Page, y: float, image_path: Path):
    pix = fitz.Pixmap(str(image_path))
    max_width = CONTENT_WIDTH
    max_height = 280
    scale = min(max_width / pix.width, max_height / pix.height, 1)
    width = pix.width * scale
    height = pix.height * scale

    if y + height + 24 > CONTENT_BOTTOM:
        page = doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        y = MARGIN_Y

    left = MARGIN_X + ((CONTENT_WIDTH - width) / 2)
    rect = fitz.Rect(left, y, left + width, y + height)
    page.insert_image(rect, filename=str(image_path))
    y += height + 16
    return page, y
