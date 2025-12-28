"""PDF extraction utilities for text, tables, and images (green-box detection + normalization).

- Renders pages with PyMuPDF (fitz) at higher resolution.
- Detects green (user-highlight) boxes on the rendered page.
- Crops each detected region, normalizes it by scaling and centering on a white canvas (CANVAS_SIZE)
  to avoid broadcasting/resizing errors.
- Runs existing is_diagram() filtering and (optional) ImageCaptioner for content-based naming.
- Keeps ONLY the final saved images (removes debug/temp artifacts).
- DOES NOT do embedded-image extraction.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import shutil

import pdfplumber
import fitz  # pymupdf

from app.ca_guidance.rag.config.settings import (
    IMAGE_OUTPUT_DIR, MIN_IMAGE_WIDTH, MIN_IMAGE_HEIGHT, MAX_ASPECT_RATIO, 
    MIN_ASPECT_RATIO, MIN_FILE_SIZE, USE_CONTENT_BASED_NAMING, OPENAI_VISION_MODEL
)
from .image_filter import is_diagram
from .image_captioner import ImageCaptioner

# OpenCV + numpy for detection and image ops
import cv2
import numpy as np

# Constants for normalization
CANVAS_SIZE = 600  # white canvas to paste normalized crops onto
RENDER_SCALE = 3.0  # rendering scale for fitz.Matrix


def _ensure_output_dir():
    IMAGE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _normalize_crop_to_canvas(crop: np.ndarray, canvas_size: int = CANVAS_SIZE) -> np.ndarray:
    """
    Resize crop to fit into canvas_size x canvas_size while preserving aspect ratio,
    then center it on a white background. Returns the final image (uint8 BGR).
    """
    # If crop is empty or invalid, return white canvas
    if crop is None or crop.size == 0:
        return np.ones((canvas_size, canvas_size, 3), dtype=np.uint8) * 255

    h, w = crop.shape[:2]
    if h == 0 or w == 0:
        return np.ones((canvas_size, canvas_size, 3), dtype=np.uint8) * 255

    # Compute scale factor (do not upscale; only downscale if larger)
    scale = min(canvas_size / w, canvas_size / h, 1.0)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    # Resize using INTER_AREA for downscaling
    resized = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Create white background and paste centered
    background = np.ones((canvas_size, canvas_size, 3), dtype=np.uint8) * 255
    x_off = (canvas_size - new_w) // 2
    y_off = (canvas_size - new_h) // 2

    background[y_off : y_off + new_h, x_off : x_off + new_w] = resized
    return background


def extract_from_pdf(pdf_path: Path, captioner: Optional[ImageCaptioner] = None) -> List[Dict[str, Any]]:
    """
    Extract text, tables (via pdfplumber) and green-box regions (via rendering + OpenCV).
    Returns list of items: {type: 'text'/'table'/'image', content/path, metadata}
    """
    _ensure_output_dir()
    items: List[Dict[str, Any]] = []

    pdf_stem = pdf_path.stem

    # Lazy init captioner if requested
    if USE_CONTENT_BASED_NAMING and captioner is None:
        try:
            from app.core.config import settings
            import os
            openai_api_key = os.getenv("OPENAI_API_KEY", getattr(settings, "OPENAI_API_KEY", None))
            if openai_api_key:
                captioner = ImageCaptioner(openai_model=OPENAI_VISION_MODEL, api_key=openai_api_key)
            else:
                print("Warning: OpenAI API key not found. Image captioning disabled.")
                captioner = None
        except Exception as e:
            print(f"Warning: Could not initialize image captioner: {e}")
            captioner = None
    
    # --- text + tables via pdfplumber ---
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            full_text_pages = []
            for i, page in enumerate(pdf.pages):
                # page text
                text = page.extract_text() or ""
                if text.strip():
                    items.append({
                        "type": "text",
                        "content": text,
                        "metadata": {"source": str(pdf_path), "page": i+1}
                    })
                # try extract table(s)
                try:
                    tables = page.extract_tables()
                except Exception:
                    tables = []
                for ti, table in enumerate(tables):
                    # convert to CSV-like string
                    rows = ["\t".join([cell if cell is not None else "" for cell in r]) for r in table]
                    table_text = "\n".join(rows)
                    # only include non-empty tables
                    if table_text.strip():
                        items.append({
                            "type": "table",
                            "content": table_text,
                            "metadata": {"source": str(pdf_path), "page": i+1, "table_index": ti}
                        })
    except Exception as e:
        print(f"pdfplumber failed on {pdf_path}: {e}")

    # --- green-box detection via rendering + OpenCV (no embedded-image extraction) ---
    try:
        doc = fitz.open(str(pdf_path))
        extracted_images: List[str] = []

        # collect page text for context for captioning
        page_texts = {}
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_texts[i + 1] = page.extract_text() or ""
        except Exception:
            pass

        for page_num in range(len(doc)):
            page = doc[page_num]
            try:
                mat = fitz.Matrix(RENDER_SCALE, RENDER_SCALE)
                page_pix = page.get_pixmap(matrix=mat)  # alpha=False by default

                # Convert pixmap -> numpy (BGR)
                img_bytes = page_pix.tobytes("png")
                nparr = np.frombuffer(img_bytes, np.uint8)
                page_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)  # BGR

                if page_img is None:
                    continue

                # Convert to HSV and threshold for green highlights (tune ranges if needed)
                hsv = cv2.cvtColor(page_img, cv2.COLOR_BGR2HSV)
                lower_green = np.array([35, 40, 40], dtype=np.uint8)
                upper_green = np.array([90, 255, 255], dtype=np.uint8)
                mask = cv2.inRange(hsv, lower_green, upper_green)

                # Morph ops: close small holes, remove noise
                kernel = np.ones((3, 3), np.uint8)
                mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

                # Find contours
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                # Collect normalized crops for this page (saved to temp files)
                normalized_crops: List[Path] = []
                for ci, c in enumerate(contours):
                    area = cv2.contourArea(c)
                    if area < 200:  # skip tiny contours; tune threshold if necessary
                        continue

                    x, y, w, h = cv2.boundingRect(c)

                    # Crop from original rendered page (best quality)
                    try:
                        crop = page_img[y : y + h, x : x + w].copy()
                    except Exception as e:
                        continue

                    # Normalize crop to white canvas (scale then center)
                    try:
                        normalized = _normalize_crop_to_canvas(crop, canvas_size=CANVAS_SIZE)
                    except Exception as e:
                        continue

                    # Save normalized crop to a temporary file (used for filtering/captioning)
                    temp_filename = IMAGE_OUTPUT_DIR / f"temp_norm_p{page_num+1}_{ci}.png"
                    try:
                        cv2.imwrite(str(temp_filename), normalized)
                        normalized_crops.append(temp_filename)
                    except Exception as e:
                        continue

                # Now filter + caption each normalized crop (use existing is_diagram + ImageCaptioner)
                for crop_index, crop_path in enumerate(normalized_crops):
                    try:
                        is_diag, filter_metadata = is_diagram(
                            str(crop_path),
                            min_width=MIN_IMAGE_WIDTH,
                            min_height=MIN_IMAGE_HEIGHT,
                            max_aspect_ratio=MAX_ASPECT_RATIO,
                            min_aspect_ratio=MIN_ASPECT_RATIO,
                        )
                    except Exception as e:
                        is_diag, filter_metadata = False, {"filter_reason": "filter_error", "error": str(e)}

                    if is_diag:
                        context_text = page_texts.get(page_num + 1, "")

                        # Decide final filename
                        if USE_CONTENT_BASED_NAMING and captioner is not None:
                            try:
                                caption = captioner.generate_caption(str(crop_path), context_text=context_text)
                                sanitized_caption = ImageCaptioner.sanitize_for_filename(caption, max_length=100)
                                final_name = f"{pdf_stem}_p{page_num+1:03d}_{sanitized_caption}_greenbox_{crop_index:02d}.png"
                            except Exception as e:
                                final_name = f"{pdf_stem}_p{page_num+1:03d}_greenbox_{crop_index:02d}.png"
                        else:
                            final_name = f"{pdf_stem}_p{page_num+1:03d}_greenbox_{crop_index:02d}.png"

                        final_path = IMAGE_OUTPUT_DIR / final_name

                        # Move temp -> final (use rename; fallback to copy)
                        try:
                            crop_path.rename(final_path)
                        except Exception:
                            try:
                                shutil.copy2(str(crop_path), str(final_path))
                                crop_path.unlink(missing_ok=True)
                            except Exception as e:
                                # ensure temp cleanup
                                try:
                                    crop_path.unlink(missing_ok=True)
                                except Exception:
                                    pass
                                continue

                        metadata = {
                            "source": str(pdf_path),
                            "page": page_num + 1,
                            "img_index": f"greenbox_{crop_index}",
                            "image_type": "diagram_greenbox",
                            **filter_metadata,
                        }

                        items.append({"type": "image", "path": str(final_path), "metadata": metadata})
                        extracted_images.append(str(final_path))
                    else:
                        # Not a diagram: delete the temp crop to save space
                        try:
                            crop_path.unlink(missing_ok=True)
                        except Exception:
                            pass

            except Exception as e:
                print(f"Green-box detection failed on page {page_num+1}: {e}")

        print(f"Extracted {len(extracted_images)} diagram(s) (green-box) from {pdf_path.name}")
    except Exception as e:
        print(f"PyMuPDF failed on {pdf_path}: {e}")

    return items

