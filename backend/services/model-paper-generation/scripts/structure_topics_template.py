"""
NOTEBOOK 2 (VS Code / Windows)
EXAM STRUCTURE + TOPIC CLUSTERS + TEMPLATES

Reads (from Notebook 1 outputs):
  data/text_extraction_hybrid/*/blueprint_with_subquestions.json  (preferred)
  OR
  data/text_extraction_hybrid/*/blueprint.json                   (fallback)

Skips bad papers:
  total marks must be EXACTLY 100 and no missing marks.

Outputs:
  data/artifacts/
    - exam_blueprint_template.json
    - topic_assignments.json
    - high_frequency_topics.json
    - template_questions.json

Requirements:
  pip install numpy pandas scikit-learn
"""

from __future__ import annotations
import json, re
from pathlib import Path
from collections import Counter
from statistics import median

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer

# Use same paths as the rest of the app (API uploads, pipeline, Docker volume /app/data)
from app.core.paths import TEXT_EXTRACTION_DIR, ARTIFACTS_DIR

# -------------------------------
# PATHS (single source of truth: app.core.paths)
# -------------------------------
BASE_DIR = Path(TEXT_EXTRACTION_DIR)   # Notebook 1 output root
OUT_ROOT = Path(ARTIFACTS_DIR)        # write outputs here
OUT_ROOT.mkdir(parents=True, exist_ok=True)


# -------------------------------
# CONFIG
# -------------------------------
EXPECTED_TOTAL_MARKS = 100
NUM_CLUSTERS = 7
TOP_K_CLUSTERS = 7
TEMPLATES_PER_CLUSTER = 3

MIN_WORDS_QUESTION_TEXT = 5

# Trend mining MUST use only the most recent K papers (deterministic sort: year + semester)
NUM_RECENT_PAPERS_FOR_TRENDS = 6


# -------------------------------
# Helpers
# -------------------------------
def _parse_year_and_semester(stem: str) -> tuple[int, int]:
    """
    Deterministic recency parsing from pdf_stem.
    Supports stems like: "2023", "2023 I", "2023 II", "2023-II", etc.
    Returns: (year, semester_rank) where semester_rank: II=2, I=1, else 0
    """
    s = (stem or "").strip()
    match = re.search(r"(20\d{2})", s)
    year = int(match.group(1)) if match else 0
    s_upper = s.upper()
    sem_rank = 0
    # Prefer II > I when present
    if re.search(r"\bII\b", s_upper) or re.search(r"[-_\s]II\b", s_upper):
        sem_rank = 2
    elif re.search(r"\bI\b", s_upper) or re.search(r"[-_\s]I\b", s_upper):
        sem_rank = 1
    return year, sem_rank

def select_recent_papers(all_papers: list[dict], k: int = NUM_RECENT_PAPERS_FOR_TRENDS) -> list[dict]:
    """
    Select the most recent k papers, deterministically sorted by (year, semester).
    """
    papers_sorted = sorted(
        all_papers,
        key=lambda p: (_parse_year_and_semester(p.get("pdf_stem", ""))[0], _parse_year_and_semester(p.get("pdf_stem", ""))[1], p.get("pdf_stem", "")),
        reverse=True,
    )
    return papers_sorted[:k]

def _aggregate_question_text(q: dict) -> str:
    """
    Deterministically assemble question text for classification when main stem is too short.
    """
    txt = clean_for_vector(q.get("text", ""))
    if len(txt.split()) >= MIN_WORDS_QUESTION_TEXT:
        return txt
    subqs = q.get("subquestions", []) or []
    if not subqs:
        return txt

    def collect_subq_texts(subqs_list):
        texts = []
        for sq in subqs_list:
            sq_text = (sq.get("text", "") or "").strip()
            if sq_text:
                texts.append(sq_text)
            nested = sq.get("subquestions", []) or []
            if nested:
                texts.extend(collect_subq_texts(nested))
        return texts

    all_subq_texts = collect_subq_texts(subqs)
    return clean_for_vector(" ".join(all_subq_texts))

def compute_topic_frequencies(recent_papers: list[dict]) -> dict:
    """
    Compute topic frequency using pattern labels from the latest papers.
    Topic definition here is the stable pattern classifier (e.g., SQL_DDL_DML, ER_EER_MODELING).
    """
    counts = Counter()
    for p in recent_papers:
        for q in p.get("questions", []):
            txt = _aggregate_question_text(q)
            if len(txt.split()) < MIN_WORDS_QUESTION_TEXT:
                continue
            counts[classify_pattern(txt)] += 1

    # Deterministic top topic selection: highest count, then alphabetically
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    top_topic = items[0][0] if items else "GENERAL_THEORY"
    return {
        "top_topic": top_topic,
        "topic_frequencies": dict(counts),
        "total_questions_counted": int(sum(counts.values())),
    }

def safe_int(x):
    try:
        if x is None:
            return None
        return int(x)
    except:
        return None

def compute_main_marks(q: dict):
    """
    Prefer q['marks'].
    If missing AND subquestions exist, sum subquestion marks.
    Else None.
    """
    mm = safe_int(q.get("marks"))
    if mm is not None:
        return mm

    subqs = q.get("subquestions", []) or []
    vals = [safe_int(s.get("marks")) for s in subqs]
    vals = [v for v in vals if v is not None]
    if vals:
        return int(sum(vals))

    return None

def clean_for_vector(text: str) -> str:
    t = text or ""
    t = re.sub(r"\[DIAGRAM:[^\]]+\]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def classify_pattern(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t).strip()

    if "relational algebra" in t or re.search(r"\bwrite.*relational algebra\b", t):
        return "RELATIONAL_ALGEBRA"
    if "functional dependenc" in t or "3nf" in t or "bcnf" in t or "attribute closure" in t:
        return "NORMALIZATION_FD_KEYS"
    if "eer" in t or "er diagram" in t or "isa constraint" in t or "aggregation" in t:
        return "ER_EER_MODELING"
    if "sql" in t or "create view" in t or "trigger" in t or "function named" in t or "query" in t:
        return "SQL_DDL_DML"
    if "serializ" in t or "schedule" in t or "transaction" in t or "locking" in t:
        return "TRANSACTIONS_CONCURRENCY"
    if "b+ tree" in t or "index" in t or "hash" in t:
        return "INDEXING_STORAGE"
    return "GENERAL_THEORY"

def get_representative_terms(model, cluster_texts, top_n=8):
    """
    Since embeddings don't give terms directly, we find the most common words 
    in the cluster, excluding stopwords.
    """
    from collections import Counter
    import re
    
    words = []
    STOPWORDS = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "by", "is", "are", "it", "this", "that", "of", "from", "as", "be", "which", "following", "given", "provide", "based", "consider", "illustrate"}
    
    for text in cluster_texts:
        # Clean and tokenize
        w = re.findall(r'\b\w{3,}\b', text.lower())
        words.extend([word for word in w if word not in STOPWORDS])
    
    most_common = Counter(words).most_common(top_n)
    return [w for w, count in most_common]


def main():
    print(">>> STRUCTURE_TOPICS_TEMPLATE STARTED <<<")

    # ==========================================================
    # STEP 1 — LOAD ALL PAPERS
    #   Prefer blueprint_with_subquestions.json
    #   Fallback to blueprint.json
    # ==========================================================
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    if not BASE_DIR.exists():
        raise FileNotFoundError(f"Notebook 1 output folder not found: {BASE_DIR}")

    paper_dirs = sorted([p for p in BASE_DIR.iterdir() if p.is_dir()])
    print("Paper folders found:", len(paper_dirs), f"(BASE_DIR={BASE_DIR})")

    papers = []
    for d in paper_dirs:
        fp_sub = d / "blueprint_with_subquestions.json"
        fp_main = d / "blueprint.json"

        fp = fp_sub if fp_sub.exists() else fp_main if fp_main.exists() else None
        if fp is None:
            continue

        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            print("⚠️ Failed to read:", fp, "|", e)
            continue

        if not data:
            continue

        # FIX: Sanitize question_id and ensure it exists
        for idx, q in enumerate(data, start=1):
            # Support both 'qno' and 'question_id' fields
            qid = q.get("qno") or q.get("question_id")
            if qid is None or str(qid).lower() == "none" or str(qid).strip() == "":
                q["question_id"] = str(idx)
            else:
                q["question_id"] = str(qid)

        pdf_stem = data[0].get("pdf_stem", d.name)
        papers.append({"pdf_stem": pdf_stem, "questions": data, "path": str(fp)})

    print("Loaded papers:", len(papers))
    if not papers:
        raise ValueError(
            "No valid blueprint.json or blueprint_with_subquestions.json found in "
            f"{BASE_DIR}. Upload past paper PDFs first, then run Generate Paper so extraction can populate this folder."
        )


    # ==========================================================
    # STEP 2 — FILTER “GOOD PAPERS”
    # ==========================================================
    paper_stats = []
    for p in papers:
        marks = [compute_main_marks(q) for q in p["questions"]]
        missing = sum(m is None for m in marks)
        total = sum(m for m in marks if isinstance(m, int))
        paper_stats.append({
            "pdf_stem": p["pdf_stem"],
            "num_questions": len(p["questions"]),
            "total_marks": total,
            "missing_marks": missing,
            "path": p["path"]
        })

    stats_df = pd.DataFrame(paper_stats).sort_values(["total_marks", "missing_marks"], ascending=[False, True])
    print("\nPer-paper stats (top 15 shown):")
    # Print in a PowerShell-friendly format to avoid truncation issues
    try:
        print(stats_df.head(15).to_string(index=False))
    except Exception as e:
        # Fallback: print row by row if DataFrame display fails
        print(f"  (Display issue: {e})")
        print("  Papers loaded:")
        for idx, row in stats_df.head(15).iterrows():
            print(f"    {row['pdf_stem']:20s} | {row['num_questions']:2d} questions | {row['total_marks']:3d} marks | {row['missing_marks']:2d} missing")

    good_df = stats_df[(stats_df["total_marks"] == EXPECTED_TOTAL_MARKS) & (stats_df["missing_marks"] == 0)].copy()
    good_stems = set(good_df["pdf_stem"].tolist())

    print(f"\nGood papers kept (total=100 and no missing): {len(good_stems)} / {len(papers)}")
    if len(good_stems) == 0:
        raise ValueError(
            "No good papers found with total=100 and missing_marks=0.\n"
            "Fix Notebook 1 marks extraction or relax the rule."
        )

    papers_good = [p for p in papers if p["pdf_stem"] in good_stems]

    # ----------------------------------------------------------
    # Trend mining + blueprint MUST use ONLY latest K papers
    # Deterministic sort: year + semester
    # ----------------------------------------------------------
    recent_papers = select_recent_papers(papers_good, k=NUM_RECENT_PAPERS_FOR_TRENDS)
    blueprint_papers = recent_papers  # Blueprint already uses latest papers; now trend mining matches.

    print(f"\nUsing recent papers for blueprint/trend computation: {len(blueprint_papers)}")

    # Persist trend summary (used downstream by orchestrator/template analyzer)
    trend = compute_topic_frequencies(recent_papers)
    trend_summary = {
        "num_recent_papers_for_trends": NUM_RECENT_PAPERS_FOR_TRENDS,
        "recent_papers_used": [p["pdf_stem"] for p in recent_papers],
        **trend,
    }
    (OUT_ROOT / "trend_summary.json").write_text(
        json.dumps(trend_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("Saved trend summary artifact.")


    # ==========================================================
    # STEP 3 — EXAM STRUCTURE TEMPLATE (Probabilistic Marking Matrix)
    # ==========================================================
    rows = []
    for p in blueprint_papers:
        for pos, q in enumerate(p["questions"], start=1):
            mm = compute_main_marks(q)
            # Structural Fingerprinting: Record sub-question splits
            subqs = q.get("subquestions", []) or []
            subq_marks = [safe_int(sq.get("marks")) for sq in subqs]
            subq_marks = [m for m in subq_marks if m is not None]
            
            rows.append({
                "pdf_stem": p["pdf_stem"],
                "question_pos": pos,
                "main_marks": mm,
                "subq_split": subq_marks,
                "num_subqs": len(subqs)
            })
    df = pd.DataFrame(rows)

    # FORCE: Always generate exactly 4 questions (Q1-Q4)
    canonical_num_questions = 4
    canonical_total_marks = int(EXPECTED_TOTAL_MARKS)

    print(f"\nFORCED: canonical_num_questions = {canonical_num_questions} (regardless of historical paper counts)")

    # Calculate slot stats for positions 1-4 (Q1-Q4) only
    # But use data from ALL positions (Q1-Q5+) for topic frequency analysis
    slot_stats = {}
    for qpos in range(1, canonical_num_questions + 1):  # Only Q1-Q4
        slot_df = df[df["question_pos"] == qpos].copy()
        marks_vals = pd.to_numeric(slot_df["main_marks"], errors="coerce").dropna().astype(int).tolist()
        if not marks_vals:
            # If no data for this position, use average from all positions or default
            all_marks = pd.to_numeric(df["main_marks"], errors="coerce").dropna().astype(int).tolist()
            if all_marks:
                marks_vals = [int(median(all_marks))]  # Use median from all positions
            else:
                marks_vals = [canonical_total_marks // canonical_num_questions]  # Even distribution
            
        # Modal Sub-question Split (Structural Fingerprint)
        split_counts = Counter([tuple(s) for s in slot_df["subq_split"].tolist() if s])
        modal_split = list(split_counts.most_common(1)[0][0]) if split_counts else []
        
        # If no subquestion data, use average from all positions
        if not modal_split:
            all_splits = [tuple(s) for s in df["subq_split"].tolist() if s]
            if all_splits:
                split_counts_all = Counter(all_splits)
                modal_split = list(split_counts_all.most_common(1)[0][0]) if split_counts_all else []

        slot_stats[qpos] = {
            "position": qpos,
            "target_marks": int(median(marks_vals)),
            "typical_num_subquestions": int(Counter(slot_df["num_subqs"]).most_common(1)[0][0]) if len(slot_df) > 0 else 3,
            "structural_fingerprint": modal_split,
            "num_samples": int(len(marks_vals))
        }

    targets = [slot_stats[pos]["target_marks"] for pos in sorted(slot_stats)]
    raw_sum = sum(targets)
    if raw_sum != canonical_total_marks and len(targets) > 0:
        delta = canonical_total_marks - raw_sum
        last_pos = sorted(slot_stats)[-1]
        slot_stats[last_pos]["target_marks"] = max(1, slot_stats[last_pos]["target_marks"] + delta)

    # ENSURE: Only create exactly 4 slots (Q1-Q4)
    exam_blueprint = {
        "component": "model_exam_paper",
        "canonical_total_marks": canonical_total_marks,
        "canonical_num_questions": canonical_num_questions,
        "bloom_guidance": "30% Understand, 40% Apply, 30% Create",
        "note": {
            "good_papers_available": len(papers_good),
            "blueprint_papers_used": [p["pdf_stem"] for p in blueprint_papers],
            "rule": f"Blueprint always generates exactly 4 questions (Q1-Q4). Topic frequency analyzed across ALL positions (Q1-Q5+) from latest {NUM_RECENT_PAPERS_FOR_TRENDS} papers. Most frequent topic forced into Q1."
        },
        "question_slots": [
            {
                "slot_id": f"Q{pos}",
                "question_no": f"Q{pos}",  # Add for compatibility
                "position": pos,
                "target_marks": slot_stats.get(pos, {}).get("target_marks", canonical_total_marks // canonical_num_questions),
                "typical_num_subquestions": slot_stats.get(pos, {}).get("typical_num_subquestions", 3),
                "structural_fingerprint": slot_stats.get(pos, {}).get("structural_fingerprint", []),
                "num_samples": slot_stats.get(pos, {}).get("num_samples", 0),
                "topics": ["General"], # Updated in Step 4
                "topic_probabilities": {}, # Updated in Step 4
                "forced_topic": False,  # Updated in Step 4
                "topic_source": "pending"  # Updated in Step 4
            }
            for pos in range(1, canonical_num_questions + 1)  # Force Q1-Q4 only
        ]
    }

    (OUT_ROOT / "exam_blueprint_template.json").write_text(
        json.dumps(exam_blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\nSaved exam_blueprint_template.json")
    print("Target marks sum:", sum([s["target_marks"] for s in exam_blueprint["question_slots"]]))


    # ==========================================================
    # STEP 4 — TOPIC DISCOVERY (TF-IDF + KMeans)
    # ==========================================================
    question_texts = []
    question_meta = []

    # Trend mining MUST use ONLY recent papers (latest K)
    for p in recent_papers:
        for pos, q in enumerate(p["questions"], start=1):
            txt = _aggregate_question_text(q)
            
            # Final check after aggregation
            if len(txt.split()) < MIN_WORDS_QUESTION_TEXT:
                continue
                
            question_texts.append(txt)
            question_meta.append({
                "pdf_stem": p["pdf_stem"],
                "question_id": str(q.get("qno") or q.get("question_id") or pos),  # Support both qno and question_id
                "question_pos": pos,
                "marks": compute_main_marks(q),
            })

    print("\nQuestions used for topic clustering:", len(question_texts))
    if len(question_texts) < NUM_CLUSTERS:
        raise ValueError("Not enough questions to form the requested number of clusters.")

    # Modern Embedding-based Clustering
    print("Vectorizing questions using SentenceTransformer (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    X = model.encode(question_texts, show_progress_bar=True)
    X = np.asarray(X, dtype="float32")

    print(f"Running KMeans (k={NUM_CLUSTERS})...")
    kmeans = KMeans(n_clusters=NUM_CLUSTERS, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X)

    # Discover themes per cluster
    cluster_terms = {}
    for c in range(NUM_CLUSTERS):
        c_texts = [txt for txt, lbl in zip(question_texts, labels) if lbl == c]
        cluster_terms[c] = get_representative_terms(model, c_texts, top_n=10)

    assignments = {}
    for meta, label, text in zip(question_meta, labels, question_texts):
        key = f"{meta['pdf_stem']}_Q{meta['question_id']}"
        assignments[key] = {
            "cluster": int(label),
            "cluster_label_keywords": cluster_terms[int(label)][:8],
            "marks": meta["marks"],
            "text": text
        }

    (OUT_ROOT / "topic_assignments.json").write_text(
        json.dumps(assignments, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("Saved topic_assignments.json")

    # ==========================================================
    # TOPIC FREQUENCY ANALYSIS (Across ALL Positions Q1-Q5+)
    # ==========================================================
    # Calculate topic frequency across ALL question positions from latest 6 papers
    all_positions_cluster_counts = Counter()
    for meta, label in zip(question_meta, labels):
        # Count clusters across ALL positions (Q1-Q5+)
        all_positions_cluster_counts[int(label)] += 1
    
    # Find the MOST FREQUENT TOPIC across all positions
    if all_positions_cluster_counts:
        most_frequent_cluster_id, most_frequent_count = all_positions_cluster_counts.most_common(1)[0]
        most_frequent_keywords = cluster_terms[most_frequent_cluster_id][:3]
        most_frequent_topic_name = ", ".join(most_frequent_keywords) if most_frequent_keywords else "General"
        print(f"\nMOST FREQUENT TOPIC (across all positions): Cluster {most_frequent_cluster_id} - '{most_frequent_topic_name}' (appears {most_frequent_count} times)")
    else:
        most_frequent_cluster_id = 0
        most_frequent_keywords = ["General"]
        most_frequent_topic_name = "General"

    # UPDATE BLUEPRINT WITH TOPICS
    # Find most common cluster for each position (Q1-Q4 only)
    pos_clusters = {}
    for meta, label in zip(question_meta, labels):
        pos = meta["question_pos"]
        if pos not in pos_clusters: pos_clusters[pos] = []
        pos_clusters[pos].append(int(label))
    
    # Track used topics to ensure uniqueness
    used_cluster_ids = set()
    
    for slot in exam_blueprint["question_slots"]:
        pos = slot["position"]
        
        # FORCE: Q1 must have the most frequent topic
        if pos == 1:
            forced_cluster_id = most_frequent_cluster_id
            forced_keywords = cluster_terms[forced_cluster_id][:3]
            slot["topics"] = forced_keywords if forced_keywords else ["General"]
            slot["forced_topic"] = True  # Mark as forced
            slot["topic_source"] = "most_frequent_across_all_positions"
            used_cluster_ids.add(forced_cluster_id)
            
            # Calculate probabilities for Q1 (from all positions, not just Q1)
            slot["topic_probabilities"] = {
                ", ".join(cluster_terms[cid][:3]): round(count / sum(all_positions_cluster_counts.values()), 2)
                for cid, count in all_positions_cluster_counts.items()
            }
            print(f"  Q1 FORCED to most frequent topic: {most_frequent_topic_name}")
        else:
            # For Q2-Q4: Use position-specific data, but avoid duplicates
            if pos in pos_clusters:
                # Get clusters for this position
                position_clusters = pos_clusters[pos]
                counts = Counter(position_clusters)
                
                # Filter out already-used clusters
                available_clusters = [(cid, count) for cid, count in counts.items() if cid not in used_cluster_ids]
                
                if available_clusters:
                    # Select most common available cluster for this position
                    selected_cluster_id, selected_count = max(available_clusters, key=lambda x: x[1])
                    selected_keywords = cluster_terms[selected_cluster_id][:3]
                    slot["topics"] = selected_keywords if selected_keywords else ["General"]
                    slot["forced_topic"] = False
                    slot["topic_source"] = f"position_{pos}_most_common"
                    used_cluster_ids.add(selected_cluster_id)
                    
                    # Probabilistic breakdown for this position
                    total_samples = len(position_clusters)
                    slot["topic_probabilities"] = {
                        ", ".join(cluster_terms[cid][:3]): round(count / total_samples, 2)
                        for cid, count in counts.items()
                    }
                else:
                    # Fallback: Use any available cluster (shouldn't happen with 7 clusters and 4 slots)
                    all_cluster_ids = set(range(NUM_CLUSTERS))
                    available = all_cluster_ids - used_cluster_ids
                    if available:
                        fallback_cluster_id = min(available)  # Pick first available
                        fallback_keywords = cluster_terms[fallback_cluster_id][:3]
                        slot["topics"] = fallback_keywords if fallback_keywords else ["General"]
                        slot["forced_topic"] = False
                        slot["topic_source"] = "fallback_unique"
                        used_cluster_ids.add(fallback_cluster_id)
                        slot["topic_probabilities"] = {}
                    else:
                        # Last resort
                        slot["topics"] = ["General"]
                        slot["forced_topic"] = False
                        slot["topic_source"] = "last_resort"
                        slot["topic_probabilities"] = {}
            else:
                # No data for this position, use fallback
                all_cluster_ids = set(range(NUM_CLUSTERS))
                available = all_cluster_ids - used_cluster_ids
                if available:
                    fallback_cluster_id = min(available)
                    fallback_keywords = cluster_terms[fallback_cluster_id][:3]
                    slot["topics"] = fallback_keywords if fallback_keywords else ["General"]
                    slot["forced_topic"] = False
                    slot["topic_source"] = "fallback_no_data"
                    used_cluster_ids.add(fallback_cluster_id)
                    slot["topic_probabilities"] = {}
                else:
                    slot["topics"] = ["General"]
                    slot["forced_topic"] = False
                    slot["topic_source"] = "last_resort"
                    slot["topic_probabilities"] = {}
    
    # Verify uniqueness
    topic_names = [", ".join(slot["topics"][:3]) for slot in exam_blueprint["question_slots"]]
    unique_topics = len(set(topic_names))
    print(f"\nTopic Uniqueness Check: {unique_topics} unique topics across 4 questions")
    if unique_topics < 4:
        print(f"  ⚠️  WARNING: Only {unique_topics} unique topics found (expected 4)")
    
    # Re-save blueprint with topics
    (OUT_ROOT / "exam_blueprint_template.json").write_text(
        json.dumps(exam_blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("Updated exam_blueprint_template.json with Probabilistic Topics")


    # ==========================================================
    # STEP 5 — HIGH FREQUENCY TOPICS
    # ==========================================================
    cluster_counts = Counter([v["cluster"] for v in assignments.values()])
    top_clusters = [c for c, _ in cluster_counts.most_common(TOP_K_CLUSTERS)]

    high_freq = {
        "top_clusters": [
            {
                "cluster_id": int(c),
                "count": int(cluster_counts[c]),
                "label_keywords": cluster_terms[int(c)][:8],
            }
            for c in top_clusters
        ]
    }

    (OUT_ROOT / "high_frequency_topics.json").write_text(
        json.dumps(high_freq, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("Saved high_frequency_topics.json")

    print("\nCluster summary:")
    for c in sorted(cluster_counts):
        print(f" - Cluster {c}: count={cluster_counts[c]} | keywords={cluster_terms[c][:8]}")


    # ==========================================================
    # STEP 6 — TEMPLATE QUESTION SELECTION
    # ==========================================================
    blueprint_index = {}
    # Templates MUST be mined from recent papers only (latest K)
    for p in recent_papers:
        for q in p["questions"]:
            blueprint_index[(p["pdf_stem"], str(q.get("question_id")))] = q

    topic_rows = []
    for key, val in assignments.items():
        pdf_stem, qid = key.rsplit("_Q", 1)
        topic_rows.append({
            "pdf_stem": pdf_stem,
            "question_id": qid,
            "cluster": val["cluster"],
            "text": val["text"],
            "text_len": len(val["text"])
        })
    topic_df = pd.DataFrame(topic_rows)

    templates = []
    # 1. Cluster-based selection (already exists)
    for c in top_clusters:
        sub = topic_df[topic_df["cluster"] == c].sort_values("text_len", ascending=False).head(TEMPLATES_PER_CLUSTER)
        for _, row in sub.iterrows():
            bp = blueprint_index.get((row["pdf_stem"], row["question_id"]), {})
            full_text = (bp.get("text") or row["text"]).strip()
            templates.append({
                "pdf_stem": row["pdf_stem"],
                "question_id": row["question_id"],
                "cluster": int(c),
                "cluster_label_keywords": cluster_terms[int(c)][:8],
                "marks": compute_main_marks(bp),
                "full_text": full_text,
                "diagram_refs": bp.get("diagram_refs", []),
                "subquestions": bp.get("subquestions", []),
                "pattern_label": classify_pattern(full_text),
            })

    # 2. Position-based selection (to ensure Q1-Q5 representation)
    # ENSURE: Prioritize recent papers for each position
    unique_positions = sorted(topic_df["question_id"].unique())
    recent_paper_stems = set(p["pdf_stem"] for p in recent_papers)
    
    for pos in unique_positions:
        # If we don't already have enough samples for this position, snag some
        current_count = sum(1 for t in templates if str(t["question_id"]) == str(pos))
        if current_count < 2:
            # Prioritize recent papers: sort by recent first, then by text length
            sub = topic_df[topic_df["question_id"] == str(pos)].copy()
            sub["is_recent"] = sub["pdf_stem"].apply(lambda x: x in recent_paper_stems)
            sub = sub.sort_values(["is_recent", "text_len"], ascending=[False, False]).head(2)
            for _, row in sub.iterrows():
                # Avoid duplicates
                if any(t["pdf_stem"] == row["pdf_stem"] and str(t["question_id"]) == str(row["question_id"]) for t in templates):
                    continue
                bp = blueprint_index.get((row["pdf_stem"], row["question_id"]), {})
                full_text = (bp.get("text") or row["text"]).strip()
                templates.append({
                    "pdf_stem": row["pdf_stem"],
                    "question_id": row["question_id"],
                    "cluster": int(row["cluster"]),
                    "cluster_label_keywords": cluster_terms[int(row["cluster"])][:8],
                    "marks": compute_main_marks(bp),
                    "full_text": full_text,
                    "diagram_refs": bp.get("diagram_refs", []),
                    "subquestions": bp.get("subquestions", []),
                    "pattern_label": classify_pattern(full_text),
                })

    (OUT_ROOT / "template_questions.json").write_text(
        json.dumps(templates, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("\nSaved template_questions.json")
    print("Templates selected:", len(templates))

    print("\nNOTEBOOK 2 COMPLETED")
    print("Outputs in:", OUT_ROOT)


if __name__ == "__main__":
    main()
