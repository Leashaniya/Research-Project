"""
Master Topic Mapper Agent
=========================
Goal: Create a `master_topic_map.json` that maps every Past Paper Question to the top 3 most relevant Lecture Slide chunks.

Features:
1. Semantic Search: Uses FAISS & embeddings to find relevant text.
2. Visual Verification: Uses VLM metadata to "boost" slides that contain similar diagrams to the question.
"""

import os
import json
import re
from pathlib import Path
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# =========================
# CONFIG
# =========================
PROJECT_ROOT = Path(__file__).resolve().parents[1].parent
DATA_ROOT = PROJECT_ROOT / "data"

# Inputs
EXTRACT_ROOT = DATA_ROOT / "text_extraction_hybrid"  # Where blueprints live
SLIDES_EXTRACT_ROOT = DATA_ROOT / "lecture_slides_extraction" # Where content lives
EMB_ROOT = DATA_ROOT / "slides_embeddings" # Where index lives

# Global Metadata Inputs
DIAGRAMS_META = EXTRACT_ROOT / "diagrams_metadata.jsonl"
FIGURES_META_FILES = SLIDES_EXTRACT_ROOT.glob("*/figures_metadata.jsonl")

# Output
OUTPUT_MAP_FILE = DATA_ROOT / "master_topic_map.json"

MODEL_NAME = "all-MiniLM-L6-v2"  # Must match what was used for embedding slides

def load_resources():
    print("⏳ Loading Resources...")
    
    # 1. Load Model
    model = SentenceTransformer(MODEL_NAME)
    
    # 2. Load FAISS Index
    index_path = EMB_ROOT / "slides_faiss_index_flatip.index"
    if not index_path.exists():
        raise FileNotFoundError(f"FAISS index not found at {index_path}")
    index = faiss.read_index(str(index_path))
    
    # 3. Load Chunks Metadata (to map ID -> Text)
    chunks_path = SLIDES_EXTRACT_ROOT / "slides_chunks.jsonl"
    chunks = []
    chunk_map = {}
    if chunks_path.exists():
        with open(chunks_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    c = json.loads(line)
                    chunks.append(c)
                    chunk_map[c["chunk_id"]] = c
    else:
         raise FileNotFoundError(f"Chunks file not found at {chunks_path}")

    # 4. Load Diagram Metadata (Exam Side) -> Map by (pdf_stem, page) or filename
    # We need to know: "Does Question X (on page P) have a diagram?"
    # Since blueprint doesn't strictly link QID to DiagramID, we can map by Page for heuristic
    exam_diagrams = []
    if DIAGRAMS_META.exists():
        with open(DIAGRAMS_META, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    exam_diagrams.append(json.loads(line))
    
    # 5. Load Slide Figure Metadata (Lecture Side) -> Map by fig_id
    slide_figures = {}
    for meta_file in FIGURES_META_FILES:
        with open(meta_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    if d.get("fig_id"):
                         slide_figures[d["fig_id"]] = d

    print(f"✅ Resources Loaded: {index.ntotal} vectors, {len(chunks)} chunks, {len(exam_diagrams)} exam diagrams.")
    return model, index, chunks, chunk_map, exam_diagrams, slide_figures

def visual_verification_boost(question_text, candidate_chunk, exam_diagrams, slide_figures, current_pdf_stem, current_page):
    """
    Returns a score boost (e.g. 0.2) if:
    1. The Question (implied by page/text) has a diagram.
    2. The Candidate Chunk contains a [FIGURE: ...] tag.
    3. The keywords in the Question Diagram's 'semantic_label' match the Slide Figure's 'caption'.
    """
    boost = 0.0
    
    # A. Does the question page have a diagram? (Heuristic: Check if any diagram is on this page)
    # Refinement: In a real agent, we'd link QID to Diagram explicitly. Here we check "Is there a diagram on Page X of Exam Y?"
    relevant_exam_diagrams = [
        d for d in exam_diagrams 
        if d.get("pdf_stem") == current_pdf_stem and d.get("page") == current_page
    ]
    
    if not relevant_exam_diagrams:
        return 0.0

    # B. Does the chunk have a figure?
    chunk_text = candidate_chunk.get("text", "")
    fig_matches = re.findall(r"\[FIGURE: (.*?)\]", chunk_text)
    
    if not fig_matches:
        return 0.0
    
    # C. Compare Semantics
    # We iterate all diagrams on the exam page and all figures in the slide chunk.
    # If ANY match meaningfully, we boost.
    
    for ed in relevant_exam_diagrams:
        e_label = (ed.get("semantic_label") or "").lower()
        e_type = (ed.get("type") or "").lower()
        
        # Simple token set for exam diagram
        e_tokens = set(re.findall(r"\w+", e_label + " " + e_type))
        # Filter generic words
        e_tokens = {t for t in e_tokens if len(t) > 3 and t not in ["diagram", "figure", "chart", "show", "below"]}

        for sf_name in fig_matches:
            sf_data = slide_figures.get(sf_name)
            if not sf_data:
                continue
                
            s_caption = (sf_data.get("caption") or "").lower()
            s_mermaid = (sf_data.get("mermaid_code") or "").lower()
            
            # Check overlap
            s_text = s_caption + " " + s_mermaid
            
            # If significant overlap
            match_count = sum(1 for t in e_tokens if t in s_text)
            
            if match_count >= 1:
                # Found a match! "Demand" in exam diagram matches "Demand" in slide caption
                boost = 0.15 # Significant boost
                # print(f"   👁️ Visual Match: '{e_label}' ~= '{s_caption[:30]}...' (+{boost})")
                return boost

    return 0.0

def main():
    model, index, chunks, chunk_map, exam_diagrams, slide_figures = load_resources()
    
    master_map = {}
    
    # Iterate over all Exam Folders
    blueprints = list(EXTRACT_ROOT.glob("*/blueprint_with_subquestions.json"))
    if not blueprints:
        print("⚠️ No blueprints found. Using non-subquestion blueprints if available...")
        blueprints = list(EXTRACT_ROOT.glob("*/blueprint.json"))
        
    for bp_path in blueprints:
        pdf_stem = bp_path.parent.name # e.g. "2018"
        print(f"\nProcessing Exam: {pdf_stem}")
        
        try:
            data = json.loads(bp_path.read_text(encoding="utf-8"))
        except Exception:
            print(f"Failed to read {bp_path}")
            continue
            
        # Flatten questions (handle both new recursive structure and old list structure)
        # We want a list of (qid, text, page)
        questions_flat = []
        
        # Flatten questions with robust ID generation
        questions_flat = []
        
        def recurse_extract(items, parent_id=""):
            for item in items:
                q_text = item.get("text") or item.get("question_text", "")
                
                # Construct ID: Use 'id' if present, else 'qno' if present, else 'label' if present
                # If parent_id exists, append label (e.g. Q1 -> Q1a)
                
                current_label = item.get("id") or str(item.get("question_id", ""))
                
                if not current_label:
                    if item.get("qno"):
                        current_label = f"Q{item['qno']}"
                    elif item.get("label"):
                         current_label = item["label"]
                    else:
                        current_label = "unk"

                if parent_id and current_label:
                    # Avoid double joining if label already contains parent
                    if current_label.startswith(parent_id):
                        full_id = current_label
                    else:
                        full_id = f"{parent_id}{current_label}"
                else:
                    full_id = current_label
                
                # If subquestions exist, recurse
                if item.get("sub_questions"):
                    recurse_extract(item["sub_questions"], full_id)
                else:
                    # Leaf Node
                    questions_flat.append({
                        "id": full_id,
                        "text": q_text,
                        "page": item.get("page", 1) 
                    })

        recurse_extract(data)
        
        # Batch Semantic Search
        # Ideally we batch encode, but for loop is fine for <100 questions
        for q in questions_flat:
            qid = q["id"]
            qtext = q["text"]
            qpage = q["page"]
            
            if not qtext or len(qtext) < 5:
                continue
                
            full_qid = f"{pdf_stem}_{qid}"
            
            # 1. Encode
            q_emb = model.encode([qtext])
            faiss.normalize_L2(q_emb)
            
            # 2. Search (Top 10)
            k = 10
            D, I = index.search(q_emb, k)
            
            candidates = []
            for i in range(k):
                idx = I[0][i]
                score = float(D[0][i])
                if idx == -1: continue
                
                # Retrieve Chunk
                chunk_data = chunks[idx]
                
                # 3. Visual Verification Boost
                boost = visual_verification_boost(
                    qtext, chunk_data, exam_diagrams, slide_figures, pdf_stem, qpage
                )
                
                final_score = score + boost
                
                candidates.append({
                    "chunk_id": chunk_data["chunk_id"],
                    "slide": chunk_data.get("slide_no"),
                    "source": Path(chunk_data["source"]).name,
                    "score": final_score,
                    "original_score": score,
                    "boost": boost,
                    "text_preview": chunk_data["text"][:100] + "..."
                })
            
            # 4. Sort and Pick Top 3 Unique Sources
            # Prefer showing diverse slides if possible? Or just top score.
            # Let's sort by final_score desc
            candidates.sort(key=lambda x: x["score"], reverse=True)
            
            top_3 = candidates[:3]
            master_map[full_qid] = top_3
            
            # Log specific visual boosts for verifying
            if any(c["boost"] > 0 for c in top_3):
                match = next(c for c in top_3 if c["boost"] > 0)
                print(f"   🚀 Visually Grounded {full_qid} -> Slide {match['slide']} (Boost: {match['boost']})")

    # Save Output
    with open(OUTPUT_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(master_map, f, indent=2)
    
    print(f"\n✅ Master Topic Map generated at: {OUTPUT_MAP_FILE}")
    print(f"Mapped {len(master_map)} questions.")

if __name__ == "__main__":
    main()
