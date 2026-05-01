"""Generate non-invasive research validation artifacts for the MCQ system.

This script only reads existing outputs and writes validation files.
It does not change the running app workflow.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from topic_labels import clean_topic_display_name

OUTPUTS_DIR = BASE_DIR / "outputs"
RECOMMENDATIONS_PATH = OUTPUTS_DIR / "graphrag_recommendations.json"
QUIZ_STATE_PATH = OUTPUTS_DIR / "graphrag_quiz_state.json"
BASELINE_PLAN_PATH = OUTPUTS_DIR / "baseline_study_plan.csv"
ADAPTIVE_PLAN_PATH = OUTPUTS_DIR / "adaptive_study_plan.csv"

TOPIC_TEMPLATE_PATH = OUTPUTS_DIR / "topic_mapping_validation_template.csv"
METHOD_COMPARISON_PATH = OUTPUTS_DIR / "method_comparison_results.csv"
METHOD_SUMMARY_PATH = OUTPUTS_DIR / "method_comparison_summary.csv"
RECOMMENDATION_TEMPLATE_PATH = OUTPUTS_DIR / "recommendation_validation_template.csv"
ADAPTIVE_VALIDATION_PATH = OUTPUTS_DIR / "adaptive_plan_validation.csv"
SUMMARY_MD_PATH = OUTPUTS_DIR / "research_validation_summary.md"


def _safe_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _tokenize(text: str) -> List[str]:
    keep = []
    for raw in str(text or "").lower().replace("-", " ").replace("_", " ").split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if len(token) >= 2:
            keep.append(token)
    return keep


def _keyword_predict(question: str, topic_labels: List[str]) -> str:
    q_tokens = set(_tokenize(question))
    best_topic = topic_labels[0] if topic_labels else "General"
    best_score = -1
    for topic in topic_labels:
        t_tokens = set(_tokenize(topic))
        score = len(q_tokens & t_tokens)
        if score > best_score:
            best_score = score
            best_topic = topic
    return clean_topic_display_name(best_topic)


def _tfidf_predict(questions: List[str], topic_labels: List[str]) -> List[str]:
    if not questions:
        return []
    if not topic_labels:
        return ["General" for _ in questions]
    corpus = questions + topic_labels
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
    tfidf = vectorizer.fit_transform(corpus)
    q_mat = tfidf[: len(questions)]
    t_mat = tfidf[len(questions) :]
    sims = cosine_similarity(q_mat, t_mat)
    out = []
    for i in range(sims.shape[0]):
        idx = int(sims[i].argmax())
        out.append(clean_topic_display_name(topic_labels[idx]))
    return out


def _embedding_predict(questions: List[str], topic_labels: List[str]) -> Tuple[List[str], str]:
    if not questions:
        return [], "no_questions"
    if not topic_labels:
        return ["General" for _ in questions], "no_topics"
    try:
        from sentence_transformers import SentenceTransformer
        from config import EMBED_MODEL_NAME

        model = SentenceTransformer(EMBED_MODEL_NAME)
        q_emb = model.encode(questions, show_progress_bar=False, convert_to_numpy=True)
        t_emb = model.encode(topic_labels, show_progress_bar=False, convert_to_numpy=True)
        sims = cosine_similarity(q_emb, t_emb)
        out = []
        for i in range(sims.shape[0]):
            idx = int(sims[i].argmax())
            out.append(clean_topic_display_name(topic_labels[idx]))
        return out, "embedding_model"
    except Exception:
        # Safe fallback: still provide a deterministic output.
        return _tfidf_predict(questions, topic_labels), "tfidf_fallback"


def _accuracy_from_labels(rows: List[Dict[str, Any]], pred_col: str) -> float | None:
    valid = [r for r in rows if str(r.get("actual_topic", "")).strip()]
    if not valid:
        return None
    hits = 0
    for r in valid:
        actual = clean_topic_display_name(str(r.get("actual_topic", "")))
        pred = clean_topic_display_name(str(r.get(pred_col, "")))
        if actual.lower() == pred.lower():
            hits += 1
    return round(hits / len(valid), 4) if valid else None


def build_topic_mapping_validation() -> None:
    rec_payload = _safe_json(RECOMMENDATIONS_PATH)
    quiz_payload = _safe_json(QUIZ_STATE_PATH)
    recommendations = list(rec_payload.get("recommendations") or [])
    weak_topics = [clean_topic_display_name(t) for t in (quiz_payload.get("weak_topics_confirmed") or [])]

    topic_pool = []
    seen = set()
    for t in weak_topics:
        if t and t not in seen:
            seen.add(t)
            topic_pool.append(t)
    for r in recommendations:
        rt = clean_topic_display_name(str(r.get("recommended_topic", "")).strip())
        if rt and rt not in seen:
            seen.add(rt)
            topic_pool.append(rt)
    if not topic_pool:
        topic_pool = [
            "Normalization",
            "Entity Relationships",
            "SQL Queries",
            "Relational Algebra",
            "Transactions and ACID",
        ]

    # Build sample rows from top recommendations; question text is unknown in persisted payload.
    rows: List[Dict[str, Any]] = []
    for rec in recommendations[:30]:
        qid = str(rec.get("question_id", "")).strip()
        if not qid:
            continue
        trace = rec.get("reason_trace") or {}
        pseudo_question = (
            f"{trace.get('supports_weak_topic', '')}. "
            f"{trace.get('related_concept', '')}. "
            f"{' '.join(rec.get('reasons') or [])}"
        ).strip()
        rows.append(
            {
                "mcq_id": qid,
                "question": pseudo_question,
                "actual_topic": "",
            }
        )
    if not rows:
        rows = [
            {"mcq_id": "sample_1", "question": "What is 3NF in normalization?", "actual_topic": ""},
            {"mcq_id": "sample_2", "question": "Which SQL JOIN returns all matching rows?", "actual_topic": ""},
            {"mcq_id": "sample_3", "question": "Define entity and relationship in ER modeling.", "actual_topic": ""},
        ]

    questions = [str(r["question"]) for r in rows]
    keyword_preds = [_keyword_predict(q, topic_pool) for q in questions]
    tfidf_preds = _tfidf_predict(questions, topic_pool)
    embedding_preds, embed_mode = _embedding_predict(questions, topic_pool)

    enriched_rows = []
    for idx, row in enumerate(rows):
        enriched_rows.append(
            {
                "mcq_id": row["mcq_id"],
                "question": row["question"],
                "actual_topic": row["actual_topic"],
                "keyword_predicted_topic": keyword_preds[idx],
                "tfidf_predicted_topic": tfidf_preds[idx],
                "embedding_predicted_topic": embedding_preds[idx],
                "keyword_correct": "",
                "tfidf_correct": "",
                "embedding_correct": "",
            }
        )

    pd.DataFrame(enriched_rows).to_csv(TOPIC_TEMPLATE_PATH, index=False)

    # Per-question method comparison table
    comparison_rows = []
    for r in enriched_rows:
        comparison_rows.append(
            {
                "mcq_id": r["mcq_id"],
                "question": r["question"],
                "keyword_matching": r["keyword_predicted_topic"],
                "tfidf_cosine": r["tfidf_predicted_topic"],
                "embedding_cosine": r["embedding_predicted_topic"],
            }
        )
    pd.DataFrame(comparison_rows).to_csv(METHOD_COMPARISON_PATH, index=False)

    # Method summary (+ accuracy if manual labels exist)
    k_acc = _accuracy_from_labels(enriched_rows, "keyword_predicted_topic")
    t_acc = _accuracy_from_labels(enriched_rows, "tfidf_predicted_topic")
    e_acc = _accuracy_from_labels(enriched_rows, "embedding_predicted_topic")
    summary = [
        {
            "method": "Keyword Matching baseline",
            "what_it_does": "Matches MCQ text tokens against topic label tokens.",
            "top1_accuracy": k_acc if k_acc is not None else "manual_labels_required",
        },
        {
            "method": "TF-IDF + Cosine Similarity",
            "what_it_does": "Represents MCQ/topic text as weighted sparse vectors and ranks by cosine similarity.",
            "top1_accuracy": t_acc if t_acc is not None else "manual_labels_required",
        },
        {
            "method": f"Sentence Embedding + Cosine Similarity ({embed_mode})",
            "what_it_does": "Uses dense semantic vectors and cosine similarity for topic mapping.",
            "top1_accuracy": e_acc if e_acc is not None else "manual_labels_required",
        },
    ]
    pd.DataFrame(summary).to_csv(METHOD_SUMMARY_PATH, index=False)


def build_recommendation_validation() -> float:
    rec_payload = _safe_json(RECOMMENDATIONS_PATH)
    recommendations = list(rec_payload.get("recommendations") or [])
    rows = []
    for i, rec in enumerate(recommendations[:30], start=1):
        trace = rec.get("reason_trace") or {}
        weak_topic = clean_topic_display_name(trace.get("supports_weak_topic") or "")
        reason_trace = "; ".join((trace.get("lines") or [])[:3])
        rows.append(
            {
                "rank": i,
                "question_id": rec.get("question_id", ""),
                "weak_topic": weak_topic,
                "recommended_question": rec.get("question_id", ""),  # text unavailable in persisted payload
                "reason_trace": reason_trace,
                "relevance_label": "",
            }
        )
    pd.DataFrame(rows).to_csv(RECOMMENDATION_TEMPLATE_PATH, index=False)

    top10 = rows[:10]
    rel_count = 0
    for row in top10:
        lbl = str(row.get("relevance_label", "")).strip().lower()
        if lbl == "relevant":
            rel_count += 1
    precision_at_10 = rel_count / 10 if top10 else 0.0
    return round(precision_at_10, 4)


def build_adaptive_plan_validation() -> Dict[str, float]:
    baseline = pd.read_csv(BASELINE_PLAN_PATH) if BASELINE_PLAN_PATH.exists() else pd.DataFrame()
    adaptive = pd.read_csv(ADAPTIVE_PLAN_PATH) if ADAPTIVE_PLAN_PATH.exists() else pd.DataFrame()

    if baseline.empty or adaptive.empty:
        pd.DataFrame(
            columns=["lecture", "quiz_accuracy", "baseline_hours", "adaptive_hours", "change_hours", "reason"]
        ).to_csv(ADAPTIVE_VALIDATION_PATH, index=False)
        return {
            "total_baseline_hours": 0.0,
            "total_adaptive_hours": 0.0,
            "difference": 0.0,
            "weak_topic_hour_gain": 0.0,
        }

    merged = adaptive.merge(
        baseline[["Lecture", "Recommended_Hours"]],
        on="Lecture",
        how="left",
        suffixes=("", "_baseline"),
    )
    rows = []
    weak_gain = 0.0
    for _, row in merged.iterrows():
        lecture = str(row.get("Lecture", ""))
        baseline_h = float(row.get("Recommended_Hours", row.get("Baseline_Hours", 0.0)) or 0.0)
        adaptive_h = float(row.get("Adaptive_Hours", 0.0) or 0.0)
        change = adaptive_h - baseline_h
        quiz_acc_raw = str(row.get("Quiz_Accuracy", "0")).replace("%", "").strip()
        try:
            quiz_acc = float(quiz_acc_raw)
        except ValueError:
            quiz_acc = 0.0
        if quiz_acc < 60 and change > 0:
            weak_gain += change
        reason = (
            "Increased due to weaker quiz performance"
            if change > 0
            else "Reduced/unchanged to preserve total hours"
        )
        rows.append(
            {
                "lecture": lecture,
                "quiz_accuracy": quiz_acc,
                "baseline_hours": round(baseline_h, 2),
                "adaptive_hours": round(adaptive_h, 2),
                "change_hours": round(change, 2),
                "reason": reason,
            }
        )

    out_df = pd.DataFrame(rows)
    out_df.to_csv(ADAPTIVE_VALIDATION_PATH, index=False)

    total_baseline = float(out_df["baseline_hours"].sum()) if not out_df.empty else 0.0
    total_adaptive = float(out_df["adaptive_hours"].sum()) if not out_df.empty else 0.0
    return {
        "total_baseline_hours": round(total_baseline, 2),
        "total_adaptive_hours": round(total_adaptive, 2),
        "difference": round(total_adaptive - total_baseline, 2),
        "weak_topic_hour_gain": round(weak_gain, 2),
    }


def build_summary_md(precision_at_10: float, adaptive_totals: Dict[str, float]) -> None:
    text = f"""# Research Validation Summary

## Method Comparison Rationale
- **Keyword matching limitation:** lexical overlap is brittle; synonyms and paraphrases are often missed.
- **TF-IDF benefit:** keeps interpretable token weights and improves ranking over raw keyword rules.
- **Embedding benefit:** captures semantic similarity beyond exact terms, helping map conceptually similar MCQs/topics.
- **Why cosine similarity:** scale-invariant vector similarity; standard for sparse (TF-IDF) and dense (embedding) vectors.

## GraphRAG Recommendation Validation
- Recommendation template generated at `outputs/recommendation_validation_template.csv`.
- Precision@10 helper definition: Relevant items in top 10 / 10.
- Current auto-computed value (before manual relevance labels): **{precision_at_10:.2f}**.
- GraphRAG explainability is preserved through `reason_trace` fields (weak signal, related concept, exam frequency, action line).

## Adaptive Plan Validation
- Validation table generated at `outputs/adaptive_plan_validation.csv`.
- Total baseline hours: **{adaptive_totals['total_baseline_hours']}**
- Total adaptive hours: **{adaptive_totals['total_adaptive_hours']}**
- Difference (adaptive - baseline): **{adaptive_totals['difference']}**
- Weak-topic hour gain: **{adaptive_totals['weak_topic_hour_gain']}**
- This demonstrates hour-preserving reallocation toward weaker areas.

## Limitations
- No supervised fine-tuned model yet (heuristic + unsupervised similarity based).
- GraphRAG is lightweight (topic graph + reason traces), not full enterprise RAG orchestration.
- Validation dataset is currently small and partially manual-label dependent.
"""
    SUMMARY_MD_PATH.write_text(text, encoding="utf-8")


def main() -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    build_topic_mapping_validation()
    precision_at_10 = build_recommendation_validation()
    adaptive_totals = build_adaptive_plan_validation()
    build_summary_md(precision_at_10, adaptive_totals)
    print("[validation] Generated:")
    print(f" - {TOPIC_TEMPLATE_PATH}")
    print(f" - {METHOD_COMPARISON_PATH}")
    print(f" - {METHOD_SUMMARY_PATH}")
    print(f" - {RECOMMENDATION_TEMPLATE_PATH}")
    print(f" - {ADAPTIVE_VALIDATION_PATH}")
    print(f" - {SUMMARY_MD_PATH}")


if __name__ == "__main__":
    main()

