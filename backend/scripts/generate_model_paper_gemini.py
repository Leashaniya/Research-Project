"""
Generate Model Paper (Gemini + Slides RAG)

Reads:
  data/artifacts/exam_blueprint_template.json
  data/artifacts/template_questions.json
  data/lecture_slides_extraction/slides_chunks.jsonl
  data/slides_embeddings/slides_faiss_index_flatip.index

Writes:
  data/outputs/model_papers/model_paper_latest_gemini.json
  data/outputs/model_papers/model_paper_latest_gemini.txt
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
import google.generativeai as genai
from app.core.config import settings


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

RECONSTRUCTED_PATH = DATA_ROOT / "diagram_reconstruction" / "reconstructed_diagrams.json"

OUT_JSON = OUT_DIR / "model_paper_latest.json"
OUT_TXT = OUT_DIR / "model_paper_latest.txt"


# -------------------------------
# Config
# -------------------------------
GEMINI_MODEL = settings.GEMINI_MODEL or "gemini-1.5-flash"
TOPK_SLIDES = 6
MAX_CONTEXT_CHARS = 10000  # Gemini has larger context, but keeping it tidy

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


def retrieve_slide_chunks(
    query: str,
    embedder: SentenceTransformer,
    index: faiss.Index,
    topk: int = TOPK_SLIDES,
) -> List[int]:
    q_emb = embedder.encode([query])
    q_emb = np.asarray(q_emb, dtype="float32")
    faiss.normalize_L2(q_emb)

    D, I = index.search(q_emb, topk)
    return [int(idx) for idx in I[0] if idx >= 0]


def format_context_from_hits(chunks: List[dict], hit_idxs: List[int]) -> str:
    parts = []
    for rank, i in enumerate(hit_idxs, start=1):
        if i < 0 or i >= len(chunks):
            continue
        c = chunks[i]
        header = f"[SLIDE_CTX {rank}] pdf={c.get('pdf_stem')} slide={c.get('slide_no')}"
        text = (c.get("text") or "").strip()
        parts.append(header + "\n" + text)
    ctx = "\n\n".join(parts).strip()
    if len(ctx) > MAX_CONTEXT_CHARS:
        ctx = ctx[:MAX_CONTEXT_CHARS] + "\n\n[CTX TRUNCATED]"
    return ctx


def pick_template_for_slot(templates: List[dict], slot_marks: int) -> dict:
    same = [t for t in templates if int(t.get("marks") or -1) == int(slot_marks)]
    pool = same if same else templates
    return random.choice(pool)


def build_prompt(slot: dict, template: dict, slide_context: str, bloom_guidance: str = "30% Understand, 40% Apply, 30% Create", mermaid_code: str = None) -> str:
    target_marks = slot["target_marks"]
    pattern = template.get("pattern_label", "GENERAL_THEORY")
    template_text = (template.get("full_text") or "").strip()
    
    # Diagram Mutation Logic
    diagram_info = ""
    if mermaid_code:
        diagram_info = f"\n- DIAGRAM MUTATION: Use this Mermaid structure but rename entities to fit your scenario:\n```mermaid\n{mermaid_code}\n```\n"
    elif "[PLACEHOLDER FIGURE]" in template_text or "diagram" in template_text.lower():
         diagram_info = "\n- Include a [PLACEHOLDER FIGURE] and describe it.\n"
    
    # 1. Structural Fingerprinting
    fingerprint = slot.get("structural_fingerprint", [])
    structure_info = ""
    if fingerprint:
        structure_info = f"\n- MANDATORY STRUCTURE: Exactly {len(fingerprint)} sub-questions with marks: {', '.join(map(str, fingerprint))}\n"

    return f"""
You are an expert University Exam Paper Setter for Database Systems.
Generate ONE high-quality question for a model exam paper.

Requirements:
- Target marks: {target_marks}
- Topic Pattern: {pattern}
- Bloom's Taxonomy Guidance: {bloom_guidance}
- Write a NEW unique question (not a copy), but follow the style/structure of the template provided.{structure_info}{diagram_info}
- Use the slide context for technical accuracy; do NOT reference "slide" or "context" explicitly.
- The question must be realistic, academic, and self-contained.
- Output MUST be valid JSON in this schema:

{{
  "question_no": "<like Q1>",
  "marks": {target_marks},
  "pattern_label": "{pattern}",
  "question_text": "<final question text with all parts and mark allocations in parentheses, e.g. (5 marks)>"
}}

Template (style reference):
{template_text}

Slide context (technical reference):
{slide_context}
""".strip()


def main():
    # Validate inputs
    must_exist(EXAM_BP_PATH, "exam_blueprint_template.json")
    must_exist(TEMPLATES_PATH, "template_questions.json")
    must_exist(SLIDES_CHUNKS_PATH, "slides_chunks.jsonl")
    must_exist(SLIDES_FAISS_PATH, "slides_faiss_index_flatip.index")

    if not settings.GOOGLE_API_KEY:
        raise EnvironmentError("GOOGLE_API_KEY is not set. Please check your .env file.")

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        generation_config={"response_mime_type": "application/json"}
    )

    print("Loading artifacts...")
    exam_bp = load_json(EXAM_BP_PATH)
    templates = load_json(TEMPLATES_PATH)
    
    reconstructed_diagrams = []
    if RECONSTRUCTED_PATH.exists():
        print("Loading reconstructed diagrams...")
        reconstructed_diagrams = load_json(RECONSTRUCTED_PATH)

    print("Loading slide chunks + FAISS...")
    slide_chunks = load_jsonl(SLIDES_CHUNKS_PATH)
    index = faiss.read_index(str(SLIDES_FAISS_PATH))

    print("Loading embedder (MiniLM)...")
    embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    slots = exam_bp["question_slots"]
    out_questions = []
    total = 0

    bloom_guidance = exam_bp.get("bloom_guidance", "30% Understand, 40% Apply, 30% Create")
    
    for i, slot in enumerate(slots, start=1):
        qno = f"Q{i}"
        target_marks = int(slot["target_marks"])

        # Topic-Slot Correlation: Pick the highest probability topic for retrieval
        topic_probs = slot.get("topic_probabilities", {})
        query_topics = slot.get("topics", ["General"])
        if topic_probs:
            # Pick the top topic string
            query_topics = [max(topic_probs, key=topic_probs.get)]

        template = pick_template_for_slot(templates, target_marks)
        
        # Match a diagram if needed
        mermaid_code = None
        if "[PLACEHOLDER FIGURE]" in template.get("full_text", "") or "diagram" in template.get("full_text", "").lower():
            # Try to find a diagram from the same pattern or random match
            matches = [r for r in reconstructed_diagrams if r.get("pattern_label") == template.get("pattern_label")]
            if not matches: matches = reconstructed_diagrams # Generic fallback
            if matches:
                mermaid_code = random.choice(matches).get("mermaid")

        retrieval_query = f"{', '.join(query_topics)} {template.get('full_text','')}"
        hit_idxs = retrieve_slide_chunks(retrieval_query, embedder, index, topk=TOPK_SLIDES)
        slide_context = format_context_from_hits(slide_chunks, hit_idxs)

        prompt = build_prompt(slot, template, slide_context, bloom_guidance, mermaid_code)

        print(f"Generating {qno} ({target_marks} marks) topic={query_topics} diagram={bool(mermaid_code)} using Gemini ({GEMINI_MODEL}) ...")
        
        try:
            response = model.generate_content(prompt)
            q_json = json.loads(response.text)
        except Exception as e:
            print(f"⚠️ Error generating {qno}: {e}")
            continue

        q_json["question_no"] = qno
        q_json["marks"] = target_marks
        q_json.setdefault("pattern_label", template.get("pattern_label", "GENERAL_THEORY"))

        out_questions.append(q_json)
        total += target_marks

    model_paper = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": GEMINI_MODEL,
        "total_marks": total,
        "questions": out_questions,
    }

    OUT_JSON.write_text(json.dumps(model_paper, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = []
    lines.append(f"MODEL EXAM PAPER (Gemini RAG)\nModel: {GEMINI_MODEL}\nTotal Marks: {total}\n" + "="*70)
    for q in out_questions:
        lines.append(f"\n{q['question_no']} ({q['marks']} marks) — {q.get('pattern_label','')}\n{q['question_text']}".strip())
    OUT_TXT.write_text("\n\n".join(lines).strip(), encoding="utf-8")

    print(f"\n✅ Done! Model paper generated with {total} total marks.")
    print(f"Saved to: {OUT_JSON}")


if __name__ == "__main__":
    main()
