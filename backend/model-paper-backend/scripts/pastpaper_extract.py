"""
Notebook 1 (Past Paper Pipeline) — VS Code Offline Script (NO POPPLER)

INPUT:
  data/past_paper_red_box/*.pdf

OUTPUT:
  data/text_extraction_hybrid/<pdf_stem>/
    pages_text/*.txt
    diagrams/*.png (+ thumbs)
    all_text_with_diagrams.txt
    cleaned_document.txt
    blueprint.json
    blueprint_with_subquestions.json

  data/text_extraction_hybrid/
    chunks.jsonl
    chunks_index.csv
    diagrams_manifest.json

QC OUTPUT:
  data/_tmp_pdf_pages_hybrid/ocr_qc_report/
    ocr_conf_report.json
    flagged_pages.txt

NOTES (Windows):
- NO Poppler needed
- Requires: pymupdf, opencv-python, pytesseract, numpy
- Tesseract OCR must be installed (and in PATH) OR set env var TESSERACT_CMD
"""


from __future__ import annotations
import sys
from pathlib import Path

# Add the backend root to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

import os, re, json, csv, time, shutil

import numpy as np
import cv2
import fitz  # PyMuPDF
import pytesseract
from pytesseract import Output
from typing import Dict, Any, Optional
from app.services.structure_service import analyze_document_structure
from app.services.vision_service import analyze_exam_diagram

# =========================
# CONFIG
# =========================
def _find_project_root(start: Path) -> Path:
    start = start.resolve()
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "frontend").exists() and (p / "backend").exists():
            return p
    # scripts -> model-paper-backend -> backend -> project_root
    return start.parents[3]

PROJECT_ROOT = _find_project_root(Path(__file__))  # .../Research Project
DATA_ROOT = PROJECT_ROOT / "data"

ROOT_PDFS = DATA_ROOT / "past_paper_red_box"
OUT_ROOT  = DATA_ROOT / "text_extraction_hybrid"
TMP_PAGES = DATA_ROOT / "_tmp_pdf_pages_hybrid"

DPI = 300
FALLBACK_DPI = 600

TESS_CONFIG = "--oem 3 --psm 6"
DO_DESKEW = True

USE_CLOUD_AI = True  # Flag to toggle Cloud AI usage

# If tesseract is not on PATH, set TESSERACT_CMD env var
# Example: setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip()
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

RED_RANGES = [
    (np.array([0, 80, 50]), np.array([10, 255, 255])),
    (np.array([170, 80, 50]), np.array([180, 255, 255]))
]
MIN_AREA = 2000
PAD = 8
THUMB_W = 512

CONF_THRESHOLD = 60
MIN_WORDS_FOR_TEXT = 12
MAX_SINGLE_BOX_FRAC = 0.70

CHUNK_WORDS = 400
OVERLAP_WORDS = 80

MIN_QUESTION_WORDS = 5
SKIP_FIRST_PAGE = True

SKIP_FILES = {
    # "some_bad_file.pdf",
}

OUT_ROOT.mkdir(parents=True, exist_ok=True)
TMP_PAGES.mkdir(parents=True, exist_ok=True)

print("PROJECT_ROOT:", PROJECT_ROOT)
print("ROOT_PDFS:", ROOT_PDFS, "exists=", ROOT_PDFS.exists())
print("TESSERACT_CMD:", TESSERACT_CMD or "using PATH")


# =========================
# Utilities (NO POPPLER)
# =========================
def pdf_to_images_pymupdf(pdf_path: Path, out_dir: Path, dpi: int):
    """
    Render every page of a PDF to PNG using PyMuPDF (NO Poppler needed).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for f in out_dir.glob("page_*.png"):
        try:
            f.unlink()
        except:
            pass

    doc = fitz.open(str(pdf_path))
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    out = []
    for i in range(doc.page_count):
        page = doc[i]
        pix = page.get_pixmap(matrix=mat, alpha=False)
        ppath = out_dir / f"page_{i+1:03d}.png"
        pix.save(str(ppath))
        out.append(ppath)

    return out


def merge_rects(rects, gap_thresh=12):
    if not rects:
        return []
    rects = sorted(rects, key=lambda r: (r[1], r[0]))
    merged = [list(rects[0])]
    for x, y, w, h in rects[1:]:
        x1, y1, w1, h1 = merged[-1]
        if x <= x1 + w1 + gap_thresh and y <= y1 + h1 + gap_thresh:
            nx = min(x, x1)
            ny = min(y, y1)
            nx2 = max(x + w, x1 + w1)
            ny2 = max(y + h, y1 + h1)
            merged[-1] = [nx, ny, nx2 - nx, ny2 - ny]
        else:
            merged.append([x, y, w, h])
    return [(int(x), int(y), int(w), int(h)) for x, y, w, h in merged]


def detect_red_boxes(img_bgr, ranges=RED_RANGES, pad=PAD, min_area=MIN_AREA):
    if img_bgr is None:
        return []

    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask_total = np.zeros(hsv.shape[:2], dtype="uint8")

    for low, high in ranges:
        mask_total = cv2.bitwise_or(mask_total, cv2.inRange(hsv, low, high))

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask_total = cv2.morphologyEx(mask_total, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask_total = cv2.dilate(mask_total, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(mask_total, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rects = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < min_area:
            continue
        rects.append((x, y, w, h))

    merged = merge_rects(rects)

    out = []
    for i, (x, y, w, h) in enumerate(sorted(merged, key=lambda r: (r[1], r[0])), start=1):
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(img_bgr.shape[1], x + w + pad), min(img_bgr.shape[0], y + h + pad)
        out.append({
            "x": int(x0),
            "y": int(y0),
            "w": int(x1 - x0),
            "h": int(y1 - y0),
            "idx": i,
            "y_mid": int(y0 + (y1 - y0) // 2),
        })
    return out


def detect_and_deskew(img):
    try:
        osd = pytesseract.image_to_osd(img)
        rot = 0
        for line in osd.splitlines():
            if "Rotate:" in line:
                rot = int(line.split(":")[1].strip())
                break
        if rot != 0:
            h, w = img.shape[:2]
            M = cv2.getRotationMatrix2D((w / 2, h / 2), -rot, 1.0)
            img = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        pass
    return img


def is_inside_any_y(yv, diagrams):
    for d in diagrams:
        if d["y"] <= yv <= (d["y"] + d["h"]):
            return True
    return False


def ocr_data_to_lines(data_dict, diagrams):
    """
    Convert Tesseract word-level data into proper line strings using line_num grouping.
    Excludes tokens inside red-box y-ranges.
    """
    n = len(data_dict.get("text", []))
    groups = {}  # key=(block, par, line) -> list of (x, word)
    confs = []

    for i in range(n):
        word = str(data_dict["text"][i]).strip()
        if not word:
            continue

        try:
            y_top = int(data_dict["top"][i])
        except:
            y_top = None

        if y_top is not None and is_inside_any_y(y_top, diagrams):
            continue

        try:
            block = int(data_dict.get("block_num", [0] * n)[i])
            par   = int(data_dict.get("par_num",   [0] * n)[i])
            line  = int(data_dict.get("line_num",  [0] * n)[i])
        except:
            block, par, line = 0, 0, 0

        try:
            x_left = int(data_dict.get("left", [0] * n)[i])
        except:
            x_left = 0

        key = (block, par, line)
        groups.setdefault(key, []).append((x_left, word))

        try:
            ci = float(data_dict["conf"][i])
            if ci >= 0:
                confs.append(ci)
        except:
            pass

    keys_sorted = sorted(groups.keys(), key=lambda k: (k[0], k[1], k[2]))
    lines = []
    for k in keys_sorted:
        words = sorted(groups[k], key=lambda t: t[0])
        line_text = " ".join([w for _, w in words]).strip()
        if line_text:
            lines.append(line_text)

    mean_conf = float(np.mean(confs)) if confs else -1
    return lines, mean_conf


# =========================
# Blueprint parser (main Q only) + marks fix + YEAR-FALSE-POSITIVE FIX ✅
# =========================
Q_MAIN_RE = re.compile(r".*\bQuestion\s*([0-9IVXLC]+)\b", re.IGNORECASE)
NUMERIC_MAIN_RE = re.compile(r"^\s*\(?\s*([0-9]+)\s*(?:[\.\)\-:])\s*", re.IGNORECASE)
ALT_Q_RE = re.compile(r".*\bQ\s*[:\.]?\s*([0-9]+)\b", re.IGNORECASE)

MARKS_RE = re.compile(r"\(?\s*([0-9]{1,3})\s*marks?\s*\)?", re.IGNORECASE)
# FIX: Allow newlines and OCR noise (e.g. 'Marksy') and optional closing paren
# This fixes 2024 Q4 where header was "o (40\nMarksy"
TOTAL_MARKS_PAREN_RE = re.compile(r"\(\s*(\d{1,3})\s*[\r\n]*\s*Marks?[a-z]*\s*\)?", re.IGNORECASE)

def _looks_like_question_total(n: int) -> bool:
    return 10 <= n <= 100

def extract_total_marks_for_question(q_lines, prev_page_tail_lines):
    header_zone = "\n".join(q_lines[:12])
    m = TOTAL_MARKS_PAREN_RE.search(header_zone)
    if m:
        val = int(m.group(1))
        if _looks_like_question_total(val):
            return val

    prev_zone = "\n".join(prev_page_tail_lines[-10:]) if prev_page_tail_lines else ""
    m2 = TOTAL_MARKS_PAREN_RE.search(prev_zone)
    if m2:
        val = int(m2.group(1))
        if _looks_like_question_total(val):
            return val

    all_marks = [int(x) for x in MARKS_RE.findall("\n".join(q_lines))]
    s = sum(all_marks)
    if _looks_like_question_total(s):
        return s
    if _looks_like_question_total(s):
        return s
    return None


def extract_subquestions(lines, total_marks_for_q=None):
    """
    Parse lines to find sub-questions starting with a), b), i., etc.
    Returns list of specific sub-question dicts.
    """
    SUB_Q_RE = re.compile(r"^\s*(\(?\s*[a-z]\s*\)|[ivx]+\.)\s*", re.IGNORECASE)
    # Regex to find marks at the end of a line or block: "(5 marks)"
    MARKS_SUB_RE = re.compile(r"\(?\s*(\d{1,3})\s*marks?\s*\)?", re.IGNORECASE)

    subs = []
    current_sub_label = None # Reverted from "intro"
    buffer = []

    def flush():
        nonlocal current_sub_label, buffer
        if current_sub_label:
            txt = "\n".join(buffer).strip()
            # Try to find marks in this sub-question block
            found_marks = MARKS_SUB_RE.findall(txt)
            m = 0
            if found_marks:
                m = sum(int(x) for x in found_marks)
            
            subs.append({
                "sub_id": current_sub_label,
                "marks": m,
                "text": txt
            })
        buffer = []
        buffer = []

    for ln in lines:
        m = SUB_Q_RE.match(ln)
        if m:
            flush()
            current_sub_label = m.group(1).strip()
            buffer.append(ln)
        else:
            if current_sub_label:
                buffer.append(ln)
    
    flush()
    return subs


def parse_blueprint_from_text(doc_text: str, pdf_stem: str, min_words=MIN_QUESTION_WORDS):
    blueprint = []
    state = {"current_q": None, "q_buffer": [], "q_page": None}

    prev_page_tail = []
    current_page_lines = []
    page_no = None

    PAGE_MARK_RE = re.compile(r"---\s*PAGE\s*([0-9]+)\s*---", re.IGNORECASE)

    def finalize():
        if state["current_q"]:
            q_text = "\n".join(state["q_buffer"]).strip()
            if not q_text:
                return

            total_marks = extract_total_marks_for_question(state["q_buffer"], prev_page_tail)
            sub_qs = extract_subquestions(state["q_buffer"], total_marks)
            
            diag_refs = [d.strip() for d in re.findall(r"\[DIAGRAM:([^\]]+)\]", q_text)]

            blueprint.append({
                "question_id": str(state["current_q"]),
                "pdf_stem": pdf_stem,
                "page_no": state["q_page"],
                "marks": int(total_marks) if total_marks is not None else None,
                "text": q_text,
                "diagram_refs": diag_refs,
                "subquestions": sub_qs
            })

        state["current_q"] = None
        state["q_buffer"] = []

    for ln in doc_text.splitlines():
        ln_strip = ln.strip()

        mpage = PAGE_MARK_RE.search(ln_strip)
        if mpage:
            prev_page_tail = current_page_lines[-20:] if current_page_lines else prev_page_tail
            current_page_lines = []
            page_no = int(mpage.group(1))
            continue

        current_page_lines.append(ln_strip)

        if not ln_strip:
            if state["current_q"]:
                state["q_buffer"].append("")
            continue

        m_qword = Q_MAIN_RE.match(ln_strip) or ALT_Q_RE.match(ln_strip)
        m_num = NUMERIC_MAIN_RE.match(ln_strip)
        
        # FIX for 2024 II: "Question 5" on line N, but "(20 Marks)" was on line N-1.
        # Or sometimes "Question 5" is on line N, marks on line N+1.
        # Current logic handles marks on N+1. We need to check if we missed marks on N-1.
        
        if m_qword:
             finalize()
             state["current_q"] = m_qword.group(1)
             state["q_page"] = page_no
             state["q_buffer"] = [ln] # Start buffer with this line
             
        # Lookback removed to restore stability.
             continue
        if m_num:
            try:
                n = int(m_num.group(1))
                if 1900 <= n <= 2100:  # looks like a year
                    m_num = None
                else:
                    # FIX: False positive check for schema lines like "(10), CAMarks:int"
                    # If the match is followed immediately by a comma, it's likely a list/schema, not a question.
                    end_idx = m_num.end()
                    rest_of_line = ln_strip[end_idx:].strip()
                    
                    if rest_of_line.startswith(","):
                        m_num = None
                    # Also check for SQL type keywords if it looks like a schema definition
                    elif re.search(r"\b(int|varchar|char|float|date)\b", rest_of_line, re.IGNORECASE):
                         m_num = None
                    # FIX for 2016 II: "3.0. The student table contains..."
                    # If the rest of the line is long (e.g., > 5 words), it's likely a sentence, not a header.
                    elif len(rest_of_line.split()) > 5:
                         m_num = None

            except Exception:
                pass

        m_main = m_qword or m_num

        if m_main:
            finalize()
            qid = m_main.group(1)
            state["current_q"] = qid
            state["q_page"] = page_no
            state["q_buffer"] = [ln_strip]
            continue

        if state["current_q"]:
            state["q_buffer"].append(ln_strip)

    finalize()
    blueprint = [b for b in blueprint if len((b.get("text") or "").split()) >= (min_words or 1)]
    return blueprint


# =========================
# Pipeline steps
# =========================
def process_one_pdf(pdf_path: Path, dpi_used=DPI):
    stem = pdf_path.stem
    print(f"\nProcessing: {pdf_path.name} (dpi={dpi_used})")

    out_pdf_dir = OUT_ROOT / stem
    pages_out = out_pdf_dir / "pages_text"
    diagrams_out = out_pdf_dir / "diagrams"
    
    # Cache Check
    combined_file = out_pdf_dir / "all_text_with_diagrams.txt"
    if combined_file.exists() and (out_pdf_dir / "pages_text").exists():
        if list((out_pdf_dir / "pages_text").glob("*.txt")):
            print(f" -> Skipping OCR: {stem} (Cache hit)")
            return True

    pages_out.mkdir(parents=True, exist_ok=True)
    diagrams_out.mkdir(parents=True, exist_ok=True)

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        print(" ⚠️ can't open PDF:", e)
        return False

    n_pages = doc.page_count

    boxed_dir = TMP_PAGES / (stem + "_boxed")
    if boxed_dir.exists():
        shutil.rmtree(boxed_dir)

    # ✅ NO POPPLER: render pages using PyMuPDF
    pdf_to_images_pymupdf(pdf_path, boxed_dir, dpi=dpi_used)

    combined_text = ""

    page_indices = list(range(1, n_pages + 1))
    if SKIP_FIRST_PAGE and page_indices:
        page_indices = page_indices[1:]

    for page_num in page_indices:
        print(" Page:", page_num)
        page = doc[page_num - 1]

        candidate = boxed_dir / f"page_{page_num:03d}.png"
        img_bgr = cv2.imread(str(candidate)) if candidate.exists() else None
        if img_bgr is None:
            print(" ⚠️ Missing rendered page image:", candidate)
            continue

        diagrams = detect_red_boxes(img_bgr)

        # 1) Try PDF text layer
        lines_ytext = []
        use_ocr = True
        page_text = ""

        try:
            blocks = page.get_text("blocks")
            text_blocks = [b for b in blocks if len(b) > 4 and str(b[4]).strip()]
            if text_blocks:
                w_img, h_img = img_bgr.shape[1], img_bgr.shape[0]
                w_pdf, h_pdf = page.rect.width, page.rect.height
                sx, sy = w_img / w_pdf, h_img / h_pdf

                for b in text_blocks:
                    x0, y0, x1, y1, txt = b[:5]
                    y_img = int(y0 * sy)
                    if not is_inside_any_y(y_img, diagrams):
                        lines_ytext.append({"y": y_img, "text": str(txt).strip()})

                lines_ytext = sorted(lines_ytext, key=lambda r: r["y"])
                page_text = "\n".join([ln["text"] for ln in lines_ytext]).strip()
                use_ocr = False
        except Exception:
            use_ocr = True
            page_text = ""

        # 2) OCR fallback (real line reconstruction)
        mean_conf = 95.0
        if use_ocr:
            mask = np.ones(img_bgr.shape[:2], dtype=np.uint8) * 255
            for d in diagrams:
                cv2.rectangle(mask, (d["x"], d["y"]), (d["x"] + d["w"], d["y"] + d["h"]), 0, -1)
            img_masked = cv2.bitwise_and(img_bgr, img_bgr, mask=mask)

            if DO_DESKEW:
                img_masked = detect_and_deskew(img_masked)

            data = pytesseract.image_to_data(img_masked, config=TESS_CONFIG, output_type=Output.DICT)
            ocr_line_texts, mean_conf = ocr_data_to_lines(data, diagrams)
            page_text = "\n".join(ocr_line_texts).strip()

        # 3) Save diagrams + placeholders
        placeholder_lines = []
        for d in diagrams:
            name = f"page_{page_num:03d}_diagram_{d['idx']}.png"
            crop = img_bgr[d["y"]:d["y"] + d["h"], d["x"]:d["x"] + d["w"]]
            cv2.imwrite(str(diagrams_out / name), crop)

            h_crop, w_crop = crop.shape[:2]
            new_w = THUMB_W
            new_h = max(1, int(h_crop * (THUMB_W / max(1, w_crop))))
            thumb = cv2.resize(crop, (new_w, new_h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(diagrams_out / name.replace(".png", "_thumb.png")), thumb)

            placeholder_lines.append((int(d["y_mid"]), f"[DIAGRAM: {name}]"))

            # --- VLM ANALYSIS (Red Box) ---
            if USE_CLOUD_AI:
                print(f"   🤖 Analyzing diagram {name}...")
                # Pass page_text as context to reduce hallucinations
                analysis = analyze_exam_diagram(diagrams_out / name, context_text=page_text)
                
                meta_entry = {
                    "pdf_stem": stem,
                    "page": page_num,
                    "filename": name,
                    "semantic_label": analysis.get("semantic_label"),
                    "student_action": analysis.get("student_action"),
                    "type": analysis.get("type"),
                    "bbox": d
                }
                
                # Global output root for metadata
                meta_jsonl = OUT_ROOT / "diagrams_metadata.jsonl"
                with open(meta_jsonl, "a", encoding="utf-8") as f:
                    f.write(json.dumps(meta_entry) + "\n")

        merged_lines = []
        if use_ocr:
            if page_text.strip():
                merged_lines.append(page_text.strip())
            for _, ph in sorted(placeholder_lines, key=lambda x: x[0]):
                merged_lines.append(ph)
            page_text = "\n".join([x for x in merged_lines if str(x).strip()]).strip()
        else:
            ph_i = 0
            ph_sorted = sorted(placeholder_lines, key=lambda x: x[0])
            for ln in lines_ytext:
                y = ln["y"]
                while ph_i < len(ph_sorted) and ph_sorted[ph_i][0] <= y:
                    merged_lines.append(ph_sorted[ph_i][1])
                    ph_i += 1
                merged_lines.append(ln["text"])
            while ph_i < len(ph_sorted):
                merged_lines.append(ph_sorted[ph_i][1])
                ph_i += 1
            page_text = "\n".join([x for x in merged_lines if str(x).strip()]).strip()

        (pages_out / f"page_{page_num:03d}_text.txt").write_text(page_text or "", encoding="utf-8")

        combined_text += f"\n\n--- PAGE {page_num} ---\n{page_text}"
        print(f" -> words: {len((page_text or '').split())} | diagrams: {len(diagrams)} | mean_conf:{mean_conf:.1f}")

    (out_pdf_dir / "all_text_with_diagrams.txt").write_text(combined_text, encoding="utf-8")
    print(" Saved:", out_pdf_dir / "all_text_with_diagrams.txt")
    return True


def run_ocr_qc(tmp_pages_root=TMP_PAGES, out_dir=None,
               conf_threshold=CONF_THRESHOLD,
               min_words_for_text=MIN_WORDS_FOR_TEXT,
               max_single_box_frac=MAX_SINGLE_BOX_FRAC):
    if out_dir is None:
        out_dir = tmp_pages_root / "ocr_qc_report"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = []
    bad = []

    for img_path in sorted(tmp_pages_root.rglob("page_*.png")):
        img = cv2.imread(str(img_path))
        if img is None:
            continue

        h, w = img.shape[:2]
        page_area = float(w * h) if (w * h) > 0 else 1.0

        diagrams = detect_red_boxes(img)

        max_single_box_area = 0.0
        for d in diagrams:
            max_single_box_area = max(max_single_box_area, (d["w"] * d["h"]))
        page_max_single_box_frac = (max_single_box_area / page_area) if page_area > 0 else 0.0

        data = pytesseract.image_to_data(img, config=TESS_CONFIG, output_type=Output.DICT)
        confs_filtered = []
        n_words = 0

        n_items = len(data.get("text", []))
        for i in range(n_items):
            txt = str(data["text"][i]).strip()
            if not txt:
                continue

            try:
                y_top = int(data["top"][i])
            except:
                y_top = None

            if y_top is not None and is_inside_any_y(y_top, diagrams):
                continue

            n_words += 1

            try:
                ci = float(data["conf"][i])
                if ci >= 0:
                    confs_filtered.append(ci)
            except:
                pass

        mean_conf = float(np.mean(confs_filtered)) if confs_filtered else -1

        rec = {
            "page": str(img_path),
            "mean_conf": mean_conf,
            "n_words": n_words,
            "max_single_box_frac": page_max_single_box_frac
        }
        report.append(rec)

        if page_max_single_box_frac >= max_single_box_frac:
            rec["flagged_reason"] = "diagram_only"
            continue
        if n_words < min_words_for_text:
            rec["flagged_reason"] = "diagram_only"
            continue

        if mean_conf < conf_threshold:
            rec["flagged_reason"] = "low_conf"
            bad.append(rec)

    (out_dir / "ocr_conf_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    with open(out_dir / "flagged_pages.txt", "w", encoding="utf-8") as f:
        for r in bad:
            f.write(
                f"{r['page']} | mean_conf={r['mean_conf']} | n_words={r.get('n_words', 0)} | "
                f"max_single_box_frac={r.get('max_single_box_frac', 0):.3f}\n"
            )

    print("OCR QC Done. Flagged pages (excluding diagram-only):", len(bad))
    return report, bad


def build_diagrams_manifest(out_root=OUT_ROOT):
    manifest_path = out_root / "diagrams_manifest.json"
    man = []

    for pdf_dir in out_root.iterdir():
        if not pdf_dir.is_dir():
            continue
        diag_folder = pdf_dir / "diagrams"
        if not diag_folder.exists():
            continue

        for f in diag_folder.glob("page_*_diagram_*.png"):
            if f.name.endswith("_thumb.png"):
                continue

            m = re.search(r"page[_\-]?0*([0-9]+)", f.name, re.IGNORECASE)
            page_no = int(m.group(1)) if m else None

            man.append({
                "pdf_stem": pdf_dir.name,
                "page_no": page_no,
                "diagram_file": str(f),
                "thumb_file": str(f).replace(".png", "_thumb.png")
            })

    manifest_path.write_text(json.dumps(man, indent=2), encoding="utf-8")
    print("Diagrams manifest written:", manifest_path)
    return manifest_path


# def build_cleaned_docs_blueprints_and_chunks(out_root=OUT_ROOT):
def build_cleaned_docs_blueprints_and_chunks(out_root=OUT_ROOT, only_pdf_stems=None):
    PAGE_TEXT_GLOB = "*/pages_text/page_*_text.txt"
    chunks_jsonl = out_root / "chunks.jsonl"
    chunks_csv = out_root / "chunks_index.csv"

    files = sorted(out_root.glob(PAGE_TEXT_GLOB))
    print(f"DEBUG: Found {len(files)} page text files total.")
    pages_by_pdf = {}

    for f in files:
        stem = f.parent.parent.name
        m = re.search(r"page[_\-]?0*([0-9]+)", f.name, re.IGNORECASE)
        page_no = int(m.group(1)) if m else None
        txt = f.read_text(encoding="utf-8", errors="ignore")
        pages_by_pdf.setdefault(stem, []).append((page_no or 0, txt, str(f)))

    global_chunks = []
    csv_rows = []

    for pdf_stem, page_list in pages_by_pdf.items():
        if only_pdf_stems is not None and pdf_stem not in only_pdf_stems:
            continue

        page_list = sorted(page_list, key=lambda x: x[0])

        doc_lines = []
        for pn, txt, _ in page_list:
            doc_lines.append(f"\n\n--- PAGE {pn} ---\n")
            s = txt.replace("\x0c", " ")
            s = re.sub(r"[^\x00-\x7F]+", " ", s)
            doc_lines.append(s)

        doc_text = "".join(doc_lines).strip()

        out_pdf_dir = out_root / pdf_stem
        cleaned_path = out_pdf_dir / "cleaned_document.txt"
        cleaned_path.write_text(doc_text, encoding="utf-8")

        blueprint_path = out_pdf_dir / "blueprint.json"
        blueprint_with_sub_path = out_pdf_dir / "blueprint_with_subquestions.json"

        if USE_CLOUD_AI and blueprint_with_sub_path.exists():
            print(f" -> Skipping AI extraction for {pdf_stem} (Cache hit)")
            blueprint_created = True
        elif USE_CLOUD_AI:
            try:
                struct_output = analyze_document_structure(doc_text)
                questions = struct_output.get("questions", [])

                # Map qno to question_id if AI used old key, and inject pdf_stem
                for idx, q in enumerate(questions, start=1):
                    q["pdf_stem"] = pdf_stem
                    if "qno" in q and "question_id" not in q:
                        q["question_id"] = str(q["qno"])
                    if not q.get("question_id"):
                        q["question_id"] = str(idx)

                # Write blueprint_with_subquestions.json
                with open(blueprint_with_sub_path, "w", encoding="utf-8") as f:
                    json.dump(questions, f, indent=2)

                # Write blueprint.json (main questions only)
                main_questions = [
                    {k: q[k] for k in q if k != "subquestions"} for q in questions
                ]
                with open(blueprint_path, "w", encoding="utf-8") as f:
                    json.dump(main_questions, f, indent=2)

                print(f"Cloud AI structuring succeeded: {len(questions)} questions")
                blueprint_created = True

            except Exception as e:
                print(f"Cloud AI structuring failed: {e}. Falling back to regex logic.")
                blueprint_created = False
        else:
            blueprint_created = False

        if not blueprint_created:
            # Fallback to regex-based blueprint parsing
            blueprint = parse_blueprint_from_text(doc_text, pdf_stem)
            with open(blueprint_path, "w", encoding="utf-8") as f:
                json.dump(blueprint, f, indent=2)

            # Write empty subquestions for fallback
            for q in blueprint:
                q["subquestions"] = []
            with open(blueprint_with_sub_path, "w", encoding="utf-8") as f:
                json.dump(blueprint, f, indent=2)

            print(f"Regex structuring succeeded: {len(blueprint)} questions")

        words = re.sub(r"\n", " \n ", doc_text).split()
        n = len(words)
        step = max(1, CHUNK_WORDS - OVERLAP_WORDS)

        start = 0
        c_i = 0
        while start < n:
            end = min(start + CHUNK_WORDS, n)
            chunk_words = words[start:end]
            chunk_text = " ".join(chunk_words).replace(" \n ", "\n").strip()

            chunk_id = f"{pdf_stem}__c{c_i:04d}"
            page_matches = re.findall(r"--- PAGE (\d+) ---", chunk_text)
            chunk_page = int(page_matches[0]) if page_matches else None

            rec = {
                "chunk_id": chunk_id,
                "pdf_stem": pdf_stem,
                "page_no": chunk_page,
                "start_word": start,
                "end_word": end,
                "n_words": len(chunk_words),
                "text": chunk_text,
                "source": str(cleaned_path)
            }
            global_chunks.append(rec)

            csv_rows.append({
                "chunk_id": chunk_id,
                "pdf_stem": pdf_stem,
                "page_no": chunk_page,
                "start_word": start,
                "end_word": end,
                "n_words": len(chunk_words),
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

    print("DONE: chunks written:", len(global_chunks))
    return True


def main_full_run(max_passes: int = 2):
    if not ROOT_PDFS.exists():
        raise FileNotFoundError(f"Input folder not found: {ROOT_PDFS}")

    pdfs = sorted(ROOT_PDFS.glob("*.pdf"))
    pdfs = [p for p in pdfs if p.name not in SKIP_FILES]

    print("Found boxed PDFs:", len(pdfs))
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found in: {ROOT_PDFS}")

    for p in pdfs:
        process_one_pdf(p, dpi_used=DPI)

    run_ocr_qc()
    build_diagrams_manifest()
    # build_cleaned_docs_blueprints_and_chunks()
    only_stems = {p.stem for p in pdfs}
    build_cleaned_docs_blueprints_and_chunks(only_pdf_stems=only_stems)


    for i in range(max_passes):
        print(f"\n=== AUTO QC PASS {i+1}/{max_passes} ===")
        _, bad = run_ocr_qc()
        if not bad:
            print("No low-confidence pages. Done.")
            break

        print("Low-confidence pages:", len(bad), "-> re-render all boxed PDFs at", FALLBACK_DPI)
        for p in pdfs:
            process_one_pdf(p, dpi_used=FALLBACK_DPI)

        time.sleep(1)
        build_diagrams_manifest()
        # build_cleaned_docs_blueprints_and_chunks()
        only_stems = {p.stem for p in pdfs}
        build_cleaned_docs_blueprints_and_chunks(only_pdf_stems=only_stems)

    print("\nPipeline finished. Outputs in:", OUT_ROOT)




def run_single(pdf_path: Path, dpi_used: int = DPI, run_qc: bool = False) -> Dict[str, Any]:

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    ok = process_one_pdf(pdf_path, dpi_used=dpi_used)
    if not ok:
        return {"status": "failed", "pdf": str(pdf_path)}

    qc_flagged: Optional[int] = None
    if run_qc:
        _, bad = run_ocr_qc()
        qc_flagged = len(bad)

    manifest_path = build_diagrams_manifest()
    # build_cleaned_docs_blueprints_and_chunks()
    build_cleaned_docs_blueprints_and_chunks(only_pdf_stems={pdf_path.stem})


    out_pdf_dir = OUT_ROOT / pdf_path.stem

    return {
        "status": "ok",
        "pdf": str(pdf_path),
        "out_dir": str(out_pdf_dir),
        "blueprint": str(out_pdf_dir / "blueprint.json"),
        "blueprint_with_subquestions": str(out_pdf_dir / "blueprint_with_subquestions.json"),
        "cleaned_document": str(out_pdf_dir / "cleaned_document.txt"),
        "all_text_with_diagrams": str(out_pdf_dir / "all_text_with_diagrams.txt"),
        "diagrams_manifest": str(manifest_path),
        "chunks_jsonl": str(OUT_ROOT / "chunks.jsonl"),
        "chunks_index_csv": str(OUT_ROOT / "chunks_index.csv"),
        "qc_flagged_pages": qc_flagged
    }

if __name__ == "__main__":
    main_full_run(max_passes=2)
