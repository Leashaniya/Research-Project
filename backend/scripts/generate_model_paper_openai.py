"""
Generate Model Paper (OpenAI + Slides RAG)

Reads:
  data/artifacts/exam_blueprint_template.json
  data/artifacts/template_questions.json
  data/lecture_slides_extraction/slides_chunks.jsonl
  data/slides_embeddings/slides_faiss_index_flatip.index

Writes:
  data/outputs/model_papers/model_paper_latest.json
  data/outputs/model_papers/model_paper_latest.txt
"""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from app.core.config import OPENAI_API_KEY


# -------------------------------
# Paths
# -------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"

ARTIFACTS_DIR = DATA_ROOT / "artifacts"
SLIDES_EXTRACT_DIR = DATA_ROOT / "lecture_slides_extraction"
SLIDES_EMB_DIR = DATA_ROOT / "slides_embeddings"

EXAM_BP_PATH = ARTIFACTS_DIR / "exam_blueprint_template.json"
TEMPLATES_PATH = ARTIFACTS_DIR / "template_questions.json"

SLIDES_CHUNKS_PATH = SLIDES_EXTRACT_DIR / "slides_chunks.jsonl"
SLIDES_FAISS_PATH = SLIDES_EMB_DIR / "slides_faiss_index_flatip.index"

OUT_DIR = DATA_ROOT / "outputs" / "model_papers"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = OUT_DIR / "model_paper_latest.json"
OUT_TXT = OUT_DIR / "model_paper_latest.txt"


# -------------------------------
# Config
# -------------------------------
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")  # change if you want
TOPK_SLIDES = 6
MAX_CONTEXT_CHARS = 7000  # keep context bounded

# Deterministic-ish
random.seed(42)


def must_exist(p: Path, label: str):
    if not p.exists():
        raise FileNotFoundError(f"{label} not found: {p}")


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def load_jsonl(p: Path) -> List[dict]:
    out = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def build_chunks_lookup(chunks: List[dict]) -> Dict[str, dict]:
    # chunk_id -> record
    return {c["chunk_id"]: c for c in chunks if "chunk_id" in c}


def retrieve_slide_chunks(
    query: str,
    embedder: SentenceTransformer,
    index: faiss.Index,
    chunks_by_id: Dict[str, dict],
    topk: int = TOPK_SLIDES,
) -> List[dict]:
    q_emb = embedder.encode([query])
    q_emb = np.asarray(q_emb, dtype="float32")
    faiss.normalize_L2(q_emb)

    D, I = index.search(q_emb, topk)
    hits = []
    for idx in I[0]:
        if idx < 0:
            continue
        # We added embeddings in the same order as slides_chunks.jsonl records were written.
        # So idx corresponds to the idx-th line in slides_chunks.jsonl.
        # We'll store that mapping by reading chunks list in order.
        # To make this robust, we will reconstruct by position later.
        hits.append(int(idx))
    return hits


def format_context_from_hits(chunks: List[dict], hit_idxs: List[int]) -> str:
    parts = []
    for rank, i in enumerate(hit_idxs, start=1):
        if i < 0 or i >= len(chunks):
            continue
        c = chunks[i]
        header = f"[SLIDE_CTX {rank}] pdf={c.get('pdf_stem')} slide={c.get('slide_no')} chunk={c.get('chunk_id')}"
        text = (c.get("text") or "").strip()
        parts.append(header + "\n" + text)
    ctx = "\n\n".join(parts).strip()
    if len(ctx) > MAX_CONTEXT_CHARS:
        ctx = ctx[:MAX_CONTEXT_CHARS] + "\n\n[CTX TRUNCATED]"
    return ctx


def pick_template_for_slot(templates: List[dict], slot_marks: int) -> dict:
    # Prefer templates with same marks; fallback to any
    same = [t for t in templates if int(t.get("marks") or -1) == int(slot_marks)]
    pool = same if same else templates
    return random.choice(pool)


def build_prompt(slot: dict, template: dict, slide_context: str) -> str:
    target_marks = slot["target_marks"]
    pattern = template.get("pattern_label", "GENERAL_THEORY")
    template_text = (template.get("full_text") or "").strip()

    return f"""
You are generating ONE question for a university model exam paper.

Requirements:
- Target marks: {target_marks}
- Pattern label: {pattern}
- Write a NEW question (not a copy), but follow the style/structure of the template.
- Use the slide context if relevant; do NOT reference "slide" or "context" explicitly.
- Make it realistic, exam-style, and self-contained.
- Output MUST be valid JSON ONLY (no markdown), in this schema:

{{
  "question_no": "<like Q1>",
  "marks": {target_marks},
  "pattern_label": "{pattern}",
  "question_text": "<final question text>"
}}

Template (style reference only):
{template_text}

Slide context (reference material):
{slide_context}
""".strip()


def openai_generate_json(client: OpenAI, prompt: str) -> dict:
    # Responses API (recommended)
    resp = client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
        temperature=0.6,
    )
    text = resp.output_text.strip()

    # Try to parse JSON; if model wrapped text, extract first {...}
    try:
        return json.loads(text)
    except Exception:
        # naive extraction
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise ValueError(f"Model did not return JSON. Got:\n{text[:800]}")


def main():
    # Validate inputs
    must_exist(EXAM_BP_PATH, "exam_blueprint_template.json")
    must_exist(TEMPLATES_PATH, "template_questions.json")
    must_exist(SLIDES_CHUNKS_PATH, "slides_chunks.jsonl")
    must_exist(SLIDES_FAISS_PATH, "slides_faiss_index_flatip.index")

    api_key = OPENAI_API_KEY
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set. Please check your .env file.")

    print("Loading artifacts...")
    exam_bp = load_json(EXAM_BP_PATH)
    templates = load_json(TEMPLATES_PATH)

    print("Loading slide chunks + FAISS...")
    slide_chunks = load_jsonl(SLIDES_CHUNKS_PATH)
    index = faiss.read_index(str(SLIDES_FAISS_PATH))

    print("Loading embedder (MiniLM)...")
    embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    print("Initializing OpenAI client...")
    client = OpenAI()

    slots = exam_bp["question_slots"]
    out_questions = []
    total = 0

    for i, slot in enumerate(slots, start=1):
        qno = f"Q{i}"
        target_marks = int(slot["target_marks"])

        template = pick_template_for_slot(templates, target_marks)

        # retrieval query: use template text + pattern
        retrieval_query = f"{template.get('pattern_label','')} {template.get('full_text','')}"
        hit_idxs = retrieve_slide_chunks(retrieval_query, embedder, index, {}, topk=TOPK_SLIDES)
        slide_context = format_context_from_hits(slide_chunks, hit_idxs)

        prompt = build_prompt(slot, template, slide_context)

        print(f"Generating {qno} ({target_marks} marks) using template {template.get('pdf_stem')} Q{template.get('question_id')} ...")
        q_json = openai_generate_json(client, prompt)

        # enforce essentials
        q_json["question_no"] = qno
        q_json["marks"] = target_marks
        q_json["pattern_label"] = template.get("pattern_label", q_json.get("pattern_label", "GENERAL_THEORY"))

        out_questions.append(q_json)
        total += target_marks

        # polite rate limiting
        time.sleep(0.2)

    model_paper = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": OPENAI_MODEL,
        "total_marks": total,
        "questions": out_questions,
    }

    OUT_JSON.write_text(json.dumps(model_paper, indent=2, ensure_ascii=False), encoding="utf-8")

    # also write a nice text version
    lines = []
    lines.append(f"MODEL EXAM PAPER (OpenAI RAG)\nModel: {OPENAI_MODEL}\nTotal Marks: {total}\n" + "="*70)
    for q in out_questions:
        lines.append(f"\n{q['question_no']} ({q['marks']} marks) — {q.get('pattern_label','')}\n{q['question_text']}".strip())
    OUT_TXT.write_text("\n\n".join(lines).strip(), encoding="utf-8")

    print("\n✅ Done!")
    print("Saved:")
    print(" -", OUT_JSON)
    print(" -", OUT_TXT)


if __name__ == "__main__":
    main()
