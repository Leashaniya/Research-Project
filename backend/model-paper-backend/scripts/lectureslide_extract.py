"""
Notebook 4 — Lecture Slides (GREEN-BOX FIGURES) → CHUNKS + EMBEDDINGS + FAISS (VS Code / Windows)

INPUT:
  data/lectureslides/*.pdf

OUTPUT:
  data/lecture_slides_extraction/<pdf_stem>/
      pages_text/slide_001_text.txt ...
      figures/slide_001_fig_1.png ...
      slides_text_with_figures.txt

  data/lecture_slides_extraction/
      slides_chunks.jsonl
      slides_chunks_index.csv

  data/slides_embeddings/
      slides_embeddings.npy
      slides_metadata.jsonl
      slides_faiss_index_flatip.index
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the backend root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

import os, re, json, csv
from pathlib import Path
from tqdm import tqdm
import numpy as np
import cv2
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from sentence_transformers import SentenceTransformer
import faiss
from app.services.vision_service import analyze_slide_diagram


# =========================
# CONFIG
# =========================
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .../Research Project
DATA_ROOT = PROJECT_ROOT / "data"

SLIDES_DIR = DATA_ROOT / "lectureslides"
OUT_ROOT   = DATA_ROOT / "lecture_slides_extraction"
EMB_ROOT   = DATA_ROOT / "slides_embeddings"

OUT_ROOT.mkdir(parents=True, exist_ok=True)
EMB_ROOT.mkdir(parents=True, exist_ok=True)

DPI = 220

GREEN_LOW  = np.array([35, 40, 40])
GREEN_HIGH = np.array([90, 255, 255])

MIN_AREA = 2500
PAD = 6
BORDER_STRIP = 4
OCR_TEXT_MIN_CHARS = 40
TESS_CONFIG = "--oem 3 --psm 6"
USE_CLOUD_AI = True # Flag to toggle Cloud AI usage

CHUNK_WORDS = 350
OVERLAP_WORDS = 70

TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip()
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

print("PROJECT_ROOT:", PROJECT_ROOT)
print("SLIDES_DIR:", SLIDES_DIR, "exists=", SLIDES_DIR.exists())
print("TESSERACT_CMD:", TESSERACT_CMD or "using PATH")


# =========================
# Utilities
# =========================
def detect_green_boxes(img_bgr, low=GREEN_LOW, high=GREEN_HIGH, min_area=MIN_AREA, pad=PAD):
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, low, high)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rects = []
    h, w = img_bgr.shape[:2]
    for c in contours:
        x, y, ww, hh = cv2.boundingRect(c)
        if ww * hh < min_area:
            continue
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(w, x + ww + pad)
        y1 = min(h, y + hh + pad)
        rects.append({
            "x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0),
            "y_mid": int(y0 + (y1 - y0) // 2)
        })

    return sorted(rects, key=lambda r: (r["y"], r["x"]))


def overlaps(b1, b2):
    x0, y0, x1, y1 = b1
    a0, b0, a1, b1_ = b2
    return not (x1 < a0 or a1 < x0 or y1 < b0 or b1_ < y0)


def rect_img_to_pdf(r_img, sx, sy):
    x0 = r_img["x"] / sx
    y0 = r_img["y"] / sy
    x1 = (r_img["x"] + r_img["w"]) / sx
    y1 = (r_img["y"] + r_img["h"]) / sy
    return (x0, y0, x1, y1)


def crop_strip_border(img, strip=BORDER_STRIP):
    h, w = img.shape[:2]
    x0 = max(0, strip)
    y0 = max(0, strip)
    x1 = max(1, w - strip)
    y1 = max(1, h - strip)
    return img[y0:y1, x0:x1]


def ocr_masked_text(img_bgr, rects_img):
    mask = np.ones(img_bgr.shape[:2], dtype=np.uint8) * 255
    for r in rects_img:
        cv2.rectangle(mask, (r["x"], r["y"]), (r["x"] + r["w"], r["y"] + r["h"]), 0, -1)

    img_masked = cv2.bitwise_and(img_bgr, img_bgr, mask=mask)

    data = pytesseract.image_to_data(img_masked, config=TESS_CONFIG, output_type=Output.DICT)
    words = []
    n = len(data.get("text", []))
    for i in range(n):
        t = str(data["text"][i]).strip()
        if not t:
            continue
        try:
            y = int(data["top"][i])
        except:
            y = 0
        words.append((y, t))

    words.sort(key=lambda x: x[0])

    lines = []
    cur = []
    last_y = None
    for y, t in words:
        if last_y is None:
            cur = [t]
            last_y = y
        elif abs(y - last_y) <= 10:
            cur.append(t)
            last_y = y
        else:
            lines.append(" ".join(cur))
            cur = [t]
            last_y = y
    if cur:
        lines.append(" ".join(cur))

    return "\n".join(lines).strip()


# =========================
# Process one slides PDF
# =========================
def process_slides_pdf(pdf_path: Path, dpi=DPI):
    stem = pdf_path.stem
    out_dir = OUT_ROOT / stem
    
    # Cache Check
    combined_file = out_dir / "slides_text_with_figures.txt"
    if combined_file.exists() and (out_dir / "pages_text").exists():
        if list((out_dir / "pages_text").glob("*.txt")):
            print(f" -> Skipping Slide Extraction: {stem} (Cache hit)")
            return True

    pages_out = out_dir / "pages_text"
    figs_out  = out_dir / "figures"
    pages_out.mkdir(parents=True, exist_ok=True)
    figs_out.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    combined = []

    for pno in range(doc.page_count):
        page = doc[pno]
        pix = page.get_pixmap(dpi=dpi, alpha=False)

        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

        rects_img = detect_green_boxes(img)

        w_img, h_img = pix.width, pix.height
        w_pdf, h_pdf = float(page.rect.width), float(page.rect.height)
        sx = (w_img / w_pdf) if w_pdf else 1.0
        sy = (h_img / h_pdf) if h_pdf else 1.0

        rects_pdf = []
        for ri in rects_img:
            x0, y0, x1, y1 = rect_img_to_pdf(ri, sx, sy)
            rects_pdf.append({
                "pdf_rect": (x0, y0, x1, y1),
                "y_mid_pdf": (y0 + y1) / 2.0,
                "img_rect": ri
            })

        blocks = page.get_text("blocks")
        lines = []
        if blocks:
            for b in blocks:
                if len(b) < 5:
                    continue
                x0, y0, x1, y1, txt = b[:5]
                txt = str(txt).strip()
                if not txt:
                    continue

                bbox = (float(x0), float(y0), float(x1), float(y1))
                inside = any(overlaps(bbox, rp["pdf_rect"]) for rp in rects_pdf)
                if inside:
                    continue
                lines.append((float(y0), txt))

            lines.sort(key=lambda x: x[0])
            page_text = "\n".join([t for _, t in lines]).strip()
        else:
            page_text = ""

        if len(page_text) < OCR_TEXT_MIN_CHARS:
            page_text = ocr_masked_text(img, [r["img_rect"] for r in rects_pdf])

        placeholders = []
        for i, rp in enumerate(rects_pdf, start=1):
            ri = rp["img_rect"]
            crop = img[ri["y"]:ri["y"] + ri["h"], ri["x"]:ri["x"] + ri["w"]]
            crop = crop_strip_border(crop, strip=BORDER_STRIP)

            fig_name = f"slide_{pno+1:03d}_fig_{i}.png"
            cv2.imwrite(str(figs_out / fig_name), crop)

            # --- VLM ANALYSIS (Green Box - Knowledge Extraction) ---
            # We treat every green box as a potential knowledge source
            if USE_CLOUD_AI:
                print(f"   🤖 Analyzing slide figure {fig_name}...")
                analysis = analyze_slide_diagram(figs_out / fig_name)
                
                meta_entry = {
                    "pdf_stem": stem,
                    "slide_no": pno + 1,
                    "fig_id": fig_name,
                    "caption": analysis.get("caption")
                }
                
                # Save to sidecar metadata file
                meta_jsonl = out_dir / "figures_metadata.jsonl" 
                with open(meta_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(meta_entry) + "\n")

            placeholders.append((rp["y_mid_pdf"], f"[FIGURE: {fig_name}]"))

        if lines:
            merged = []
            ph_i = 0
            placeholders.sort(key=lambda x: x[0])

            for y0, txt in lines:
                while ph_i < len(placeholders) and placeholders[ph_i][0] <= y0:
                    merged.append(placeholders[ph_i][1])
                    ph_i += 1
                merged.append(txt)

            while ph_i < len(placeholders):
                merged.append(placeholders[ph_i][1])
                ph_i += 1

            final_text = "\n".join([m for m in merged if str(m).strip()]).strip()
        else:
            ph_text = "\n".join([p[1] for p in sorted(placeholders, key=lambda x: x[0])])
            final_text = (ph_text + "\n" + page_text).strip() if ph_text else page_text

        slide_file = pages_out / f"slide_{pno+1:03d}_text.txt"
        slide_file.write_text(final_text, encoding="utf-8")

        combined.append(f"\n\n--- SLIDE {pno+1} ---\n{final_text}")

    (out_dir / "slides_text_with_figures.txt").write_text("".join(combined).strip(), encoding="utf-8")
    print(f"✅ {stem}: slides={doc.page_count}")
    return True


def build_slides_chunks(chunk_words=CHUNK_WORDS, overlap_words=OVERLAP_WORDS):
    chunks_jsonl = OUT_ROOT / "slides_chunks.jsonl"
    chunks_csv   = OUT_ROOT / "slides_chunks_index.csv"

    all_text_files = sorted(OUT_ROOT.glob("*/slides_text_with_figures.txt"))
    if not all_text_files:
        raise FileNotFoundError("No slides_text_with_figures.txt found. Run extraction first.")

    global_chunks = []
    csv_rows = []

    # 1. Load Figure Metadata Map (Filename -> Caption)
    fig_meta_map = {}
    for meta_file in OUT_ROOT.glob("*/figures_metadata.jsonl"):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data = json.loads(line)
                        # key = "slide_001_fig_1.png"
                        fid = data.get("fig_id")
                        caption = data.get("caption")
                        
                        if fid and caption:
                            fig_meta_map[fid] = f"Figure Description: {caption}"
        except Exception:
            pass

    for tf in all_text_files:
        pdf_stem = tf.parent.name
        doc_text = tf.read_text(encoding="utf-8", errors="ignore")

        words = re.sub(r"\n", " \n ", doc_text).split()
        n = len(words)
        step = max(1, chunk_words - overlap_words)

        start = 0
        c_i = 0
        while start < n:
            end = min(start + chunk_words, n)
            chunk_words_list = words[start:end]
            chunk_text = " ".join(chunk_words_list).replace(" \n ", "\n").strip()

            # --- METADATA INJECTION ---
            # Find [FIGURE: slide_XXX_fig_Y.png] tags in this chunk
            fig_tags = re.findall(r"\[FIGURE: (.*?)\]", chunk_text)
            for fig_name in fig_tags:
                if fig_name in fig_meta_map:
                    # Append the semantic description to the chunk so FAISS can index it
                    enrichment = f"\n[SEMANTIC ENRICHMENT]: {fig_meta_map[fig_name]}"
                    chunk_text += enrichment

            slide_matches = re.findall(r"--- SLIDE (\d+) ---", chunk_text)
            slide_no = int(slide_matches[0]) if slide_matches else None

            chunk_id = f"{pdf_stem}__sc{c_i:04d}"
            rec = {
                "chunk_id": chunk_id,
                "pdf_stem": pdf_stem,
                "slide_no": slide_no,
                "start_word": start,
                "end_word": end,
                "n_words": len(chunk_words_list),
                "text": chunk_text,
                "source": str(tf),
            }
            global_chunks.append(rec)

            csv_rows.append({
                "chunk_id": chunk_id,
                "pdf_stem": pdf_stem,
                "slide_no": slide_no,
                "start_word": start,
                "end_word": end,
                "n_words": len(chunk_words_list),
                "text_snippet": (chunk_text[:200] + "...") if len(chunk_text) > 200 else chunk_text,
            })

            c_i += 1
            start += step

    with open(chunks_jsonl, "w", encoding="utf-8") as jf:
        for rec in global_chunks:
            jf.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(chunks_csv, "w", newline="", encoding="utf-8") as cf:
        writer = csv.DictWriter(cf, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["chunk_id"])
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"✅ slides_chunks.jsonl written: {len(global_chunks)} chunks")
    return chunks_jsonl


def build_slides_embeddings_and_faiss(chunks_jsonl: Path):
    chunks = []
    with open(chunks_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                chunks.append(json.loads(line))

    texts = [c["text"] for c in chunks]
    print("Loaded slide chunks:", len(chunks))

    print("Loading SBERT...")
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    print("Encoding...")
    embs = model.encode(texts, batch_size=16, show_progress_bar=True)
    embs = np.asarray(embs, dtype="float32")

    emb_path = EMB_ROOT / "slides_embeddings.npy"
    meta_path = EMB_ROOT / "slides_metadata.jsonl"
    faiss_path = EMB_ROOT / "slides_faiss_index_flatip.index"

    np.save(str(emb_path), embs)

    with open(meta_path, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({
                "chunk_id": c["chunk_id"],
                "pdf_stem": c["pdf_stem"],
                "slide_no": c["slide_no"],
                "source": c["source"],
            }, ensure_ascii=False) + "\n")

    faiss.normalize_L2(embs)
    d = embs.shape[1]
    index = faiss.IndexFlatIP(d)
    index.add(embs)
    faiss.write_index(index, str(faiss_path))

    print("✅ Saved:")
    print(" -", emb_path)
    print(" -", meta_path)
    print(" -", faiss_path)


# =========================
# NEW: run_single for API usage
# =========================
def run_single(pdf_path: Path):
    """
    API-friendly: process exactly ONE PDF, then rebuild chunks+embeddings.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    process_slides_pdf(pdf_path)

    # rebuild global chunks + embeddings (includes this new pdf)
    chunks_path = build_slides_chunks()
    build_slides_embeddings_and_faiss(chunks_path)

    return {
        "pdf": str(pdf_path),
        "status": "success",
        "outputs": {
            "chunks": str(OUT_ROOT / "slides_chunks.jsonl"),
            "index": str(EMB_ROOT / "slides_faiss_index_flatip.index"),
            "metadata": str(EMB_ROOT / "slides_metadata.jsonl"),
        }
    }


# =========================
# Batch MAIN
# =========================
def main():
    if not SLIDES_DIR.exists():
        raise FileNotFoundError(f"Slides folder not found: {SLIDES_DIR}")

    slide_pdfs = sorted(SLIDES_DIR.glob("*.pdf"))
    print("Slides PDFs found:", len(slide_pdfs))
    if not slide_pdfs:
        raise FileNotFoundError(f"No PDFs found in {SLIDES_DIR}")

    for pdf in tqdm(slide_pdfs, desc="Slides PDFs"):
        process_slides_pdf(pdf)

    chunks_path = build_slides_chunks()
    build_slides_embeddings_and_faiss(chunks_path)

    print("\n✅ NOTEBOOK 4 COMPLETED")
    print("Outputs:")
    print(" -", OUT_ROOT / "<pdf_stem>/slides_text_with_figures.txt")
    print(" -", OUT_ROOT / "slides_chunks.jsonl")
    print(" -", EMB_ROOT / "slides_faiss_index_flatip.index")


if __name__ == "__main__":
    main()
