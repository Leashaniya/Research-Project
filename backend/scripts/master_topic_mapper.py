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
import openai

# =========================
# CONFIG
# =========================
PROJECT_ROOT = Path(__file__).resolve().parents[1].parent
DATA_ROOT = PROJECT_ROOT / "data"

# Inputs
EXTRACT_ROOT = DATA_ROOT / "text_extraction_hybrid"
SLIDES_EXTRACT_ROOT = DATA_ROOT / "lecture_slides_extraction"
EMB_ROOT = DATA_ROOT / "slides_embeddings"

# Global Metadata Inputs
DIAGRAMS_META = EXTRACT_ROOT / "diagrams_metadata.jsonl"
FIGURES_META_FILES = SLIDES_EXTRACT_ROOT.glob("*/figures_metadata.jsonl")

# Output
OUTPUT_MAP_FILE = DATA_ROOT / "master_topic_map.json"

MODEL_NAME = "all-MiniLM-L6-v2"

# API Key Check
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / "backend" / ".env")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

if OPENAI_API_KEY:
    client = openai.OpenAI(api_key=OPENAI_API_KEY, base_url="https://api.openai.com/v1")
else:
    print("WARNING: OPENAI_API_KEY not found. Helper keyword extraction will fail.")
    client = None

# =========================
# ANCHORING RULES
# =========================
TOPIC_ANCHORS = {
    "EER": [2],
    "Relational Mapping": [2],
    "Normalization": [3],
    "Schema Refinement": [3],
    "BCNF": [3],
    "3NF": [3],
    "Relational Algebra": [4],
    "SQL": [4],
    "Concurrency": [7, 9],
    "Transaction": [7, 9],
    "2PL": [7, 9],
    "Locking": [7, 9],
    "Deadlock": [7, 9],
    "Schedule": [7, 9],
    "Serializ": [7, 9] # Serializable, Serialization
}

def load_resources():
    print("⏳ Loading Resources...")
    
    # 1. Load Model
    model = SentenceTransformer(MODEL_NAME)
    
    # 2. Load FAISS Index
    index_path = EMB_ROOT / "slides_faiss_index_flatip.index"
    if not index_path.exists():
        raise FileNotFoundError(f"FAISS index not found at {index_path}")
    index = faiss.read_index(str(index_path))
    
    # 3. Load Chunks Metadata
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

    # 4. Load Diagram Metadata (Exam Side)
    exam_diagrams = []
    if DIAGRAMS_META.exists():
        with open(DIAGRAMS_META, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    exam_diagrams.append(json.loads(line))
    
    # 5. Load Slide Figure Metadata (Lecture Side)
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

def extract_technical_keywords(text):
    """
    Uses LLM to extract core technical terms to use as search queries.
    """
    if not client:
        return text # Fallback
        
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a Technical Keyword Extractor for Database Systems. Extract 3-5 core technical concepts (e.g. '2PL', 'Relational Algebra', '3NF', 'EER') from the question text. Return ONLY the keywords separated by spaces. Do not include filler words."},
                {"role": "user", "content": f"Question: {text}"}
            ],
            temperature=0.0,
            max_tokens=50
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"LLM Keyword Extraction Failed: {e}")
        return text

def visual_verification_boost(question_text, candidate_chunk, exam_diagrams, slide_figures, current_pdf_stem, current_page):
    """
    Returns +0.3 boost if diagram semantic labels match slide figures.
    """
    boost = 0.0
    
    # A. Check if Question implies a diagram (now using direct check on page/stem since we don't have per-question diagram link in flat list easily yet)
    # The 'questions_flat' struct below has 'page', so we use that.
    
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
    for ed in relevant_exam_diagrams:
        e_label = (ed.get("semantic_label") or "").lower()
        e_type = (ed.get("type") or "").lower()
        if not e_label: continue

        for sf_name in fig_matches:
            sf_data = slide_figures.get(sf_name)
            if not sf_data: continue
                
            s_caption = (sf_data.get("caption") or "").lower()
            s_mermaid = (sf_data.get("mermaid_code") or "").lower()
            s_text = s_caption + " " + s_mermaid
            
            # Simple keyword overlap
            e_keywords = set(re.findall(r"\w+", e_label))
            # Filter stop words
            e_keywords = {k for k in e_keywords if len(k) > 2 and k not in ["diagram", "figure", "table", "graph", "show", "following"]}
            
            if not e_keywords: continue

            # If any significant keyword from exam diagram appears in slide figure
            if any(k in s_text for k in e_keywords):
                return 0.3 # Requested Boost

    return 0.0

def main():
    model, index, chunks, chunk_map, exam_diagrams, slide_figures = load_resources()
    
    master_map = {}
    
    # Iterate over all Exam Folders
    blueprints = list(EXTRACT_ROOT.glob("*/blueprint_with_subquestions.json"))
    if not blueprints:
        print("⚠️ No blueprints with subquestions found. Using standard blueprints.")
        blueprints = list(EXTRACT_ROOT.glob("*/blueprint.json"))
        
    for bp_path in blueprints:
        pdf_stem = bp_path.parent.name
        print(f"\nProcessing Exam: {pdf_stem}")
        
        try:
            data = json.loads(bp_path.read_text(encoding="utf-8"))
        except:
            continue
            
        # Flatten questions
        questions_flat = []
        def recurse_extract(items, parent_id=""):
            for item in items:
                q_text = item.get("text") or item.get("question_text", "")
                current_label = item.get("id") or str(item.get("question_id", ""))
                
                # Robust naming
                if not current_label and item.get("qno"): current_label = f"Q{item['qno']}"
                if not current_label: current_label = "unk"
                
                if parent_id and not current_label.startswith(str(parent_id)):
                    full_id = f"{parent_id}.{current_label}" if parent_id else current_label
                else:
                    full_id = current_label
                
                if item.get("subquestions"):
                    recurse_extract(item["subquestions"], full_id)
                else:
                    questions_flat.append({
                        "id": full_id,
                        "text": q_text,
                        "page": item.get("page", 1), # Default to 1 if missing,
                        "diagrams": item.get("diagrams", []) # Capture diagram tags if strictly mapped
                    })

        recurse_extract(data)
        
        for q in tqdm(questions_flat, desc=f"Mapping {pdf_stem}"):
            qid = q["id"]
            qtext = q["text"]
            qpage = q["page"]
            
            if not qtext or len(qtext) < 5: continue
            
            full_qid = f"{pdf_stem}_{qid}"
            
            # 1. LLM Keyword Extraction
            search_query = extract_technical_keywords(qtext)
            # print(f"   Query for {qid}: {search_query}")
            
            # 2. Encode & Search
            q_emb = model.encode([search_query])
            faiss.normalize_L2(q_emb)
            k = 10
            D, I = index.search(q_emb, k)
            
            candidates = []
            for i in range(k):
                idx = I[0][i]
                raw_score = float(D[0][i])
                if idx == -1: continue
                
                c_data = chunks[idx]
                chunk_txt = c_data["text"]
                slide_no = c_data.get("slide_no", -1)
                lecture_source = Path(c_data["source"]).stem # e.g. "Lecture 02 - EER"
                
                current_score = raw_score
                
                # --- HEURISTICS ---
                
                # A. Weighted Semantic Search (1.5x)
                # Check if keywords appear in chunk text
                keywords = set(search_query.lower().split())
                matches = sum(1 for kw in keywords if kw in chunk_txt.lower())
                if matches > 0:
                    current_score *= 1.5
                
                # B. Lecture Anchoring
                # Check known mappings
                for topic, lecture_ids in TOPIC_ANCHORS.items():
                    if topic.lower() in search_query.lower() or topic.lower() in qtext.lower():
                        # Check if this slide is from a target lecture (simplified check by filename number or content)
                        # Assuming filename structure "Lecture XX" or similar, or relying on metadata. 
                        # We try to extract lecture number from filename
                        lec_num_match = re.search(r"Lecture\s*0?(\d+)", lecture_source, re.IGNORECASE)
                        if lec_num_match:
                            lec_num = int(lec_num_match.group(1))
                            if lec_num in lecture_ids:
                                current_score += 0.4 # Anchor Boost
                                # print(f"      ⚓ Anchor: {topic} matched Lecture {lec_num}")

                # C. Visual Boost (+0.3)
                v_boost = visual_verification_boost(qtext, c_data, exam_diagrams, slide_figures, pdf_stem, qpage)
                current_score += v_boost
                
                candidates.append({
                    "chunk_id": c_data["chunk_id"],
                    "slide": slide_no,
                    "source": Path(c_data["source"]).name,
                    "score": current_score,
                    "raw_score": raw_score,
                    "text_preview": chunk_txt[:100] + "..."
                })
            
            # Sort by boosted score
            candidates.sort(key=lambda x: x["score"], reverse=True)
            master_map[full_qid] = candidates[:3]

    # Save
    with open(OUTPUT_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(master_map, f, indent=2)
    
    print(f"\n✅ Master Topic Map generated at: {OUTPUT_MAP_FILE}")
    print(f"Mapped {len(master_map)} questions.")

if __name__ == "__main__":
    main()

