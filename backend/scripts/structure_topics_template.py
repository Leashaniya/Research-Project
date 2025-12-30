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
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans


# -------------------------------
# PATHS (Project-relative)
# -------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../Research Project
DATA_ROOT = PROJECT_ROOT / "data"

BASE_DIR = DATA_ROOT / "text_extraction_hybrid"     # Notebook 1 output root
OUT_ROOT = DATA_ROOT / "artifacts"                 # write outputs here
OUT_ROOT.mkdir(parents=True, exist_ok=True)


# -------------------------------
# CONFIG
# -------------------------------
EXPECTED_TOTAL_MARKS = 100
NUM_CLUSTERS = 4
TOP_K_CLUSTERS = 4
TEMPLATES_PER_CLUSTER = 3

MIN_WORDS_QUESTION_TEXT = 5
TFIDF_MIN_DF = 2
TFIDF_MAX_DF = 0.9
TFIDF_NGRAM_RANGE = (1, 2)


# -------------------------------
# Helpers
# -------------------------------
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

def top_terms_per_cluster(X, labels, vectorizer, top_n=8):
    terms = np.array(vectorizer.get_feature_names_out())
    out = {}
    for c in sorted(set(labels)):
        idx = np.where(labels == c)[0]
        if len(idx) == 0:
            out[c] = []
            continue
        mean_tfidf = X[idx].mean(axis=0)
        arr = np.asarray(mean_tfidf).ravel()
        top_idx = arr.argsort()[::-1][:top_n]
        out[c] = [terms[i] for i in top_idx if arr[i] > 0]
    return out


def main():
    print(">>> STRUCTURE_TOPICS_TEMPLATE STARTED <<<")

    # ==========================================================
    # STEP 1 — LOAD ALL PAPERS
    #   Prefer blueprint_with_subquestions.json
    #   Fallback to blueprint.json
    # ==========================================================
    if not BASE_DIR.exists():
        raise FileNotFoundError(f"Notebook 1 output folder not found: {BASE_DIR}")

    paper_dirs = sorted([p for p in BASE_DIR.iterdir() if p.is_dir()])
    print("Paper folders found:", len(paper_dirs))

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

        pdf_stem = data[0].get("pdf_stem", d.name)
        papers.append({"pdf_stem": pdf_stem, "questions": data, "path": str(fp)})

    print("Loaded papers:", len(papers))
    if not papers:
        raise ValueError("No valid blueprint.json or blueprint_with_subquestions.json found.")


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
    print(stats_df.head(15).to_string(index=False))

    good_df = stats_df[(stats_df["total_marks"] == EXPECTED_TOTAL_MARKS) & (stats_df["missing_marks"] == 0)].copy()
    good_stems = set(good_df["pdf_stem"].tolist())

    print(f"\nGood papers kept (total=100 and no missing): {len(good_stems)} / {len(papers)}")
    if len(good_stems) == 0:
        raise ValueError(
            "No good papers found with total=100 and missing_marks=0.\n"
            "Fix Notebook 1 marks extraction or relax the rule."
        )

    papers_good = [p for p in papers if p["pdf_stem"] in good_stems]


    # ==========================================================
    # STEP 3 — EXAM STRUCTURE TEMPLATE
    # ==========================================================
    rows = []
    for p in papers_good:
        for pos, q in enumerate(p["questions"], start=1):
            mm = compute_main_marks(q)
            rows.append({
                "pdf_stem": p["pdf_stem"],
                "question_pos": pos,
                "main_marks": mm,
                "num_subqs": len(q.get("subquestions", []) or [])
            })
    df = pd.DataFrame(rows)

    num_qs = [len(p["questions"]) for p in papers_good]
    canonical_num_questions = int(pd.Series(num_qs).mode()[0])
    canonical_total_marks = int(EXPECTED_TOTAL_MARKS)

    slot_stats = {}
    for qpos in range(1, canonical_num_questions + 1):
        slot_df = df[df["question_pos"] == qpos].copy()
        marks_vals = pd.to_numeric(slot_df["main_marks"], errors="coerce").dropna().astype(int).tolist()
        if not marks_vals:
            continue
        slot_stats[qpos] = {
            "position": qpos,
            "target_marks": int(median(marks_vals)),
            "typical_num_subquestions": int(Counter(slot_df["num_subqs"]).most_common(1)[0][0]),
            "num_samples": int(len(marks_vals))
        }

    targets = [slot_stats[pos]["target_marks"] for pos in sorted(slot_stats)]
    raw_sum = sum(targets)
    if raw_sum != canonical_total_marks and len(targets) > 0:
        delta = canonical_total_marks - raw_sum
        last_pos = sorted(slot_stats)[-1]
        slot_stats[last_pos]["target_marks"] = max(1, slot_stats[last_pos]["target_marks"] + delta)

    exam_blueprint = {
        "component": "model_exam_paper",
        "canonical_total_marks": canonical_total_marks,
        "canonical_num_questions": canonical_num_questions,
        "note": {
            "good_papers_used": int(len(papers_good)),
            "skipped_papers": int(len(papers) - len(papers_good)),
            "rule": "Only papers with total=100 and missing_marks=0 were used for structure + topics"
        },
        "question_slots": [
            {
                "slot_id": f"Q{pos}",
                "position": pos,
                "target_marks": slot_stats[pos]["target_marks"],
                "typical_num_subquestions": slot_stats[pos]["typical_num_subquestions"],
                "num_samples": slot_stats[pos]["num_samples"],
            }
            for pos in sorted(slot_stats)
        ]
    }

    (OUT_ROOT / "exam_blueprint_template.json").write_text(
        json.dumps(exam_blueprint, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\n✅ Saved exam_blueprint_template.json")
    print("Target marks sum:", sum([s["target_marks"] for s in exam_blueprint["question_slots"]]))


    # ==========================================================
    # STEP 4 — TOPIC DISCOVERY (TF-IDF + KMeans)
    # ==========================================================
    question_texts = []
    question_meta = []

    for p in papers_good:
        for q in p["questions"]:
            txt = clean_for_vector(q.get("text", ""))
            if len(txt.split()) < MIN_WORDS_QUESTION_TEXT:
                continue
            question_texts.append(txt)
            question_meta.append({
                "pdf_stem": p["pdf_stem"],
                "question_id": str(q.get("question_id")),
                "marks": compute_main_marks(q),
            })

    print("\nQuestions used for topic clustering:", len(question_texts))
    if len(question_texts) < NUM_CLUSTERS:
        raise ValueError("Not enough questions to form the requested number of clusters.")

    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_df=TFIDF_MAX_DF,
        min_df=TFIDF_MIN_DF,
        ngram_range=TFIDF_NGRAM_RANGE
    )
    X = vectorizer.fit_transform(question_texts)

    kmeans = KMeans(n_clusters=NUM_CLUSTERS, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X)

    cluster_terms = top_terms_per_cluster(X, labels, vectorizer, top_n=10)

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
    print("✅ Saved topic_assignments.json")


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
    print("✅ Saved high_frequency_topics.json")

    print("\nCluster summary:")
    for c in sorted(cluster_counts):
        print(f" - Cluster {c}: count={cluster_counts[c]} | keywords={cluster_terms[c][:8]}")


    # ==========================================================
    # STEP 6 — TEMPLATE QUESTION SELECTION
    # ==========================================================
    blueprint_index = {}
    for p in papers_good:
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

    (OUT_ROOT / "template_questions.json").write_text(
        json.dumps(templates, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print("\n✅ Saved template_questions.json")
    print("Templates selected:", len(templates))

    print("\n✅ NOTEBOOK 2 COMPLETED")
    print("Outputs in:", OUT_ROOT)


if __name__ == "__main__":
    main()
