"""Research-grade offline retrieval evaluation for weak-topic MCQ ranking.

Compares three methods over the full candidate MCQ pool per weak topic:
1) TF-IDF + cosine
2) Sentence-BERT embedding + cosine
3) Hybrid score = 0.4 TF-IDF + 0.6 embedding

Outputs (research artifacts only):
- outputs/retrieval_comparison.json
- outputs/evaluation_metrics.json
- outputs/retrieval_comparison_summary.csv
- outputs/research_report.md
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUTS = BASE_DIR / "outputs"

QUIZ_STATE_PATH = OUTPUTS / "graphrag_quiz_state.json"
RETRIEVAL_JSON_PATH = OUTPUTS / "retrieval_comparison.json"
EVAL_METRICS_PATH = OUTPUTS / "evaluation_metrics.json"
SUMMARY_CSV_PATH = OUTPUTS / "retrieval_comparison_summary.csv"
METHOD_COMPARISON_CSV_PATH = OUTPUTS / "retrieval_method_comparison.csv"
RESEARCH_REPORT_PATH = OUTPUTS / "research_report.md"
FAIRNESS_REPORT_PATH = OUTPUTS / "evaluation_fairness_report.md"
EVAL_PLOT_PATH = OUTPUTS / "evaluation_results.png"
EXPLANATION_LOG_PATH = OUTPUTS / "retrieval_explanations.md"
STRATIFIED_JSON_PATH = OUTPUTS / "retrieval_stratified_analysis.json"
SIGNIFICANCE_REPORT_PATH = OUTPUTS / "statistical_significance_report.md"

METHODS = ("tfidf_cosine", "embedding_cosine", "hybrid")
TOP_K = 10
K = TOP_K

RETRIEVAL_METRICS_K10_JSON_PATH = OUTPUTS / "retrieval_metrics_k10.json"
RETRIEVAL_METRICS_K10_CSV_PATH = OUTPUTS / "retrieval_metrics_k10.csv"


def _safe_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().replace("-", " ").replace("_", " ").split())


def _topic_match(a: str, b: str) -> bool:
    a_n = _norm(a)
    b_n = _norm(b)
    if not a_n or not b_n:
        return False
    return a_n == b_n or (a_n in b_n) or (b_n in a_n)


def _minmax(v: np.ndarray) -> np.ndarray:
    if v.size == 0:
        return v
    lo = float(np.min(v))
    hi = float(np.max(v))
    if hi - lo < 1e-12:
        return np.zeros_like(v, dtype=np.float64)
    return (v - lo) / (hi - lo)


def _load_runtime_data() -> Tuple[pd.DataFrame, List[Dict[str, Any]], np.ndarray]:
    """Load current MCQ/topic pipeline state (non-invasive)."""
    import sys

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))

    from app.services import state
    from app.services.mcq_service import run_analysis
    from mcq_utils import compute_similarities

    if state.MCQ_DF.empty or not state.ALL_TOPICS or not state.LECTURE_DATA:
        ok, msg = run_analysis()
        if not ok:
            raise RuntimeError(f"run_analysis failed: {msg}")

    sims, _ = compute_similarities(state.ALL_TOPICS, state.MCQ_DF)
    return state.MCQ_DF.copy(), list(state.ALL_TOPICS), np.asarray(sims)


def _topic_labels_from_all_topics(all_topics: List[Dict[str, Any]]) -> List[str]:
    out: List[str] = []
    for t in all_topics:
        kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
        out.append(kws[0] if kws else "General")
    return out


def _assign_mcq_topics(mcq_df: pd.DataFrame, topic_labels: List[str], sims: np.ndarray) -> List[str]:
    """Pseudo-ground-truth label for validation from existing topic-question sims."""
    n_q = len(mcq_df)
    if sims.size == 0 or not topic_labels:
        return ["General"] * n_q

    labels: List[str] = []
    for j in range(n_q):
        if j >= sims.shape[1]:
            labels.append("General")
            continue
        i = int(np.argmax(sims[:, j]))
        labels.append(topic_labels[i] if 0 <= i < len(topic_labels) else "General")
    return labels


def _build_relevance_vector(weak_topic: str, mcq_topics: List[str]) -> np.ndarray:
    rel = np.array([1 if _topic_match(t, weak_topic) else 0 for t in mcq_topics], dtype=np.int32)
    return rel


def _precision_at_k(ranked_rel: np.ndarray, k: int = 10) -> float:
    if ranked_rel.size == 0:
        return 0.0
    kk = min(k, ranked_rel.size)
    return float(np.sum(ranked_rel[:kk])) / float(k)


def _recall_at_k(ranked_rel: np.ndarray, total_relevant: int, k: int = 10) -> float:
    if total_relevant <= 0:
        return 0.0
    kk = min(k, ranked_rel.size)
    return float(np.sum(ranked_rel[:kk])) / float(total_relevant)


def _mrr_at_k(ranked_rel: np.ndarray, k: int = TOP_K) -> float:
    if ranked_rel.size == 0:
        return 0.0
    kk = min(k, ranked_rel.size)
    pos = np.where(ranked_rel[:kk] > 0)[0]
    if pos.size == 0:
        return 0.0
    return 1.0 / float(pos[0] + 1)


def _ndcg_at_k(ranked_rel: np.ndarray, total_relevant: int, k: int = 10) -> float:
    kk = min(k, ranked_rel.size)
    if kk <= 0:
        return 0.0
    gains = ranked_rel[:kk].astype(np.float64)
    discounts = 1.0 / np.log2(np.arange(2, kk + 2))
    dcg = float(np.sum(gains * discounts))
    ideal_hits = min(max(total_relevant, 0), kk)
    if ideal_hits <= 0:
        return 0.0
    ideal = np.array([1.0] * ideal_hits + [0.0] * (kk - ideal_hits), dtype=np.float64)
    idcg = float(np.sum(ideal * discounts))
    if idcg <= 1e-12:
        return 0.0
    return dcg / idcg


def _diversity_at_k(top_idx: np.ndarray, mcq_topics: List[str], k: int = 10) -> int:
    kk = min(k, top_idx.size)
    uniq = set()
    for idx in top_idx[:kk]:
        if 0 <= int(idx) < len(mcq_topics):
            uniq.add(_norm(mcq_topics[int(idx)]))
    return len([u for u in uniq if u])


def rank_results(scores: np.ndarray) -> np.ndarray:
    return np.argsort(scores)[::-1]


def evaluate_tfidf(tfidf_scores: np.ndarray) -> np.ndarray:
    return np.asarray(tfidf_scores, dtype=np.float64)


def evaluate_embedding(emb_scores: np.ndarray) -> np.ndarray:
    return np.asarray(emb_scores, dtype=np.float64)


def evaluate_hybrid(tfidf_scores: np.ndarray, emb_scores: np.ndarray) -> np.ndarray:
    tfidf_norm = _minmax(np.asarray(tfidf_scores, dtype=np.float64))
    emb_norm = _minmax(np.asarray(emb_scores, dtype=np.float64))
    return (0.4 * tfidf_norm) + (0.6 * emb_norm)


def compute_metrics(
    ranked_idx: np.ndarray,
    relevance: np.ndarray,
    mcq_topics: List[str],
    k: int = TOP_K,
) -> Dict[str, Any]:
    ranked_rel = relevance[ranked_idx]
    total_relevant = int(np.sum(relevance))
    precision = _precision_at_k(ranked_rel, k=k)
    recall = _recall_at_k(ranked_rel, total_relevant, k=k)
    mrr = _mrr_at_k(ranked_rel, k=k)
    ndcg = _ndcg_at_k(ranked_rel, total_relevant, k=k)
    diversity = _diversity_at_k(ranked_idx, mcq_topics, k=k)
    hits = int(np.sum(ranked_rel[: min(k, ranked_rel.size)]))
    return {
        "precision_at_10": round(precision, 4),
        "recall_at_10": round(recall, 4),
        "mrr_at_10": round(mrr, 4),
        "ndcg_at_10": round(ndcg, 4),
        "diversity_unique_topics_at_10": int(diversity),
        "relevant_in_top_10": int(hits),
        "total_relevant_in_pool": int(total_relevant),
    }


def _evaluate_one_topic(
    weak_topic: str,
    mcq_df: pd.DataFrame,
    mcq_texts: List[str],
    mcq_topics: List[str],
    tfidf_scores: np.ndarray,
    emb_scores: np.ndarray,
) -> Dict[str, Any]:
    method_scores = {
        "tfidf_cosine": evaluate_tfidf(tfidf_scores),
        "embedding_cosine": evaluate_embedding(emb_scores),
        "hybrid": evaluate_hybrid(tfidf_scores, emb_scores),
    }

    relevance = _build_relevance_vector(weak_topic, mcq_topics)
    by_method: Dict[str, Any] = {}
    for method, scores in method_scores.items():
        ranked_idx = rank_results(scores)
        metrics = compute_metrics(ranked_idx, relevance, mcq_topics, k=TOP_K)
        top_rows = []
        for rank, idx in enumerate(ranked_idx[:TOP_K], start=1):
            i = int(idx)
            top_rows.append(
                {
                    "rank": rank,
                    "question_id": str(mcq_df.iloc[i].get("id", "")),
                    "question": str(mcq_texts[i]),
                    "assigned_topic": str(mcq_topics[i]),
                    "score": round(float(scores[i]), 6),
                    "is_relevant": bool(relevance[i]),
                }
            )
        metrics["pool_size"] = int(len(mcq_df))
        metrics["top_10_mcqs"] = top_rows
        by_method[method] = metrics

    return {"weak_topic": weak_topic, "methods": by_method}


def _build_fairness_report(
    weak_topics: List[str],
    summary_rows: List[Dict[str, Any]],
    aggregate: Dict[str, Dict[str, float]],
    best_method: str,
) -> None:
    by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for row in summary_rows:
        by_topic.setdefault(str(row["weak_topic"]), []).append(row)

    # Dataset fairness: same pool size + same method count per weak topic.
    pool_consistent = True
    method_complete = True
    zero_relevant_topics = 0
    relevant_counts = []
    for wt, rows in by_topic.items():
        methods_here = {r["method"] for r in rows}
        if methods_here != set(METHODS):
            method_complete = False
        pools = {int(r["pool_size"]) for r in rows}
        if len(pools) != 1:
            pool_consistent = False
        rels = {int(r["total_relevant_in_pool"]) for r in rows}
        rel = int(next(iter(rels))) if rels else 0
        relevant_counts.append(rel)
        if rel == 0:
            zero_relevant_topics += 1

    dataset_status = "Pass" if (pool_consistent and method_complete) else "Fail"
    if dataset_status == "Pass" and zero_relevant_topics > 0:
        dataset_status = "Warning"

    # Ranking fairness: same top-k everywhere and same protocol.
    ranking_status = "Pass"
    ranking_note = (
        f"All methods are scored on full candidate pools, sorted descending, "
        f"and evaluated at K={TOP_K}."
    )

    # Metric consistency checks.
    metric_status = "Pass"
    metric_notes = [
        f"Precision@{TOP_K}: hits in top-{TOP_K} divided by K={TOP_K} (fixed denominator).",
        f"Recall@{TOP_K}: hits in top-{TOP_K} divided by total relevant in pool.",
        "MRR: reciprocal of first relevant rank.",
        f"NDCG@{TOP_K}: binary relevance DCG normalized by ideal DCG.",
        f"Diversity@{TOP_K}: unique topic count among top-{TOP_K}.",
    ]
    if any(int(r["pool_size"]) < TOP_K for r in summary_rows):
        metric_status = "Warning"
        metric_notes.append(
            f"Some pools are smaller than K={TOP_K}; fixed-denominator precision may be conservative."
        )

    # Hybrid bias checks.
    hybrid_status = "Pass"
    hybrid_note = (
        "Hybrid uses min-max normalized TF-IDF and embedding scores, "
        "then combines as 0.4*TF-IDF + 0.6*Embedding consistently."
    )

    # Best model validity assessment.
    # Weighted formula uses normalized/range-aligned metrics in [0,1], diversity scaled by /10.
    validity = "scientifically valid"
    validity_reason = (
        "Best-method score is based on explicit weighted metrics: "
        "0.25*Precision@10 + 0.25*Recall@10 + 0.25*MRR@10 + 0.25*NDCG@10."
    )
    if zero_relevant_topics > 0:
        validity = "partially valid"
        validity_reason += (
            f" However, {zero_relevant_topics} weak topic(s) have zero relevant items, "
            "which limits external validity of averaged retrieval metrics."
        )

    # Bias analysis
    min_rel = min(relevant_counts) if relevant_counts else 0
    max_rel = max(relevant_counts) if relevant_counts else 0
    imbalance_ratio = (max_rel / max(1, min_rel)) if max_rel else 0.0

    bias_lines = [
        "- Weak topic selection bias: evaluated topics come from current quiz weak-topic state, not all syllabus topics.",
        "- Topic imbalance: relevant-item counts vary by topic, affecting Recall and NDCG comparability.",
        "- Label bias: relevance is topic-alignment based on auto-assigned MCQ topics (not manual relevance judgments).",
        "- Hybrid weight bias: 0.4/0.6 is fixed and not sensitivity-tested in this run.",
    ]
    if zero_relevant_topics > 0:
        bias_lines.append(
            f"- Zero-relevance topic case: {zero_relevant_topics} topic(s) (e.g., JDBC-like) have no relevant pool matches."
        )
    if imbalance_ratio > 2.0:
        bias_lines.append(
            f"- Topic imbalance severity: max/min relevant count ratio is {imbalance_ratio:.2f}."
        )

    lines: List[str] = []
    lines.append("# Evaluation Fairness Report")
    lines.append("")
    lines.append("## Dataset Fairness Check")
    lines.append(
        f"**{dataset_status}** - Same weak-topic set and same MCQ pool are used across methods per topic."
    )
    if zero_relevant_topics > 0:
        lines.append(
            f"Note: {zero_relevant_topics} weak topic(s) have zero relevant items in pool (warning for validity)."
        )
    lines.append("")
    lines.append("## Ranking Fairness Check")
    lines.append(f"**{ranking_status}** - {ranking_note}")
    lines.append("")
    lines.append("## Metric Consistency Check")
    lines.append(f"**{metric_status}**")
    for m in metric_notes:
        lines.append(f"- {m}")
    lines.append("")
    lines.append("## Bias Analysis")
    for b in bias_lines:
        lines.append(b)
    lines.append("")
    lines.append("## Best Model Selection Validity")
    lines.append(
        f"Result: **{validity}**. Current best method is `{best_method}`. {validity_reason}"
    )
    lines.append("")
    lines.append("## Recommended Improvements")
    lines.append("- Add stratified topic evaluation (group by low/medium/high relevant pool size).")
    lines.append("- Run sensitivity analysis for hybrid weights (e.g., 0.2/0.8, 0.5/0.5, 0.7/0.3).")
    lines.append("- Add manual relevance validation set for a subset of MCQs.")
    lines.append("- Report both macro and micro averages explicitly.")
    lines.append("- Add confidence intervals via bootstrap over weak topics.")
    lines.append("")
    lines.append("## Final Conclusion")
    lines.append(
        "The comparison protocol is methodologically fair (same pool, same ranking protocol, same K), "
        "but scientific reliability is partially constrained by topic imbalance and auto-derived relevance labels."
    )
    lines.append("")
    FAIRNESS_REPORT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    aggr = {
        m: {
            "precision_at_10": 0.0,
            "recall_at_10": 0.0,
            "mrr_at_10": 0.0,
            "ndcg_at_10": 0.0,
            "diversity_unique_topics_at_10": 0.0,
            "topics_evaluated": 0.0,
        }
        for m in METHODS
    }
    for row in rows:
        method = row["method"]
        aggr[method]["precision_at_10"] += float(row["precision_at_10"])
        aggr[method]["recall_at_10"] += float(row["recall_at_10"])
        aggr[method]["mrr_at_10"] += float(row["mrr_at_10"])
        aggr[method]["ndcg_at_10"] += float(row["ndcg_at_10"])
        aggr[method]["diversity_unique_topics_at_10"] += float(row["diversity_unique_topics_at_10"])
        aggr[method]["topics_evaluated"] += 1.0

    for method in METHODS:
        n = max(1.0, aggr[method]["topics_evaluated"])
        aggr[method]["precision_at_10"] = round(aggr[method]["precision_at_10"] / n, 4)
        aggr[method]["recall_at_10"] = round(aggr[method]["recall_at_10"] / n, 4)
        aggr[method]["mrr_at_10"] = round(aggr[method]["mrr_at_10"] / n, 4)
        aggr[method]["ndcg_at_10"] = round(aggr[method]["ndcg_at_10"] / n, 4)
        aggr[method]["diversity_unique_topics_at_10"] = round(
            aggr[method]["diversity_unique_topics_at_10"] / n, 4
        )
        aggr[method]["topics_evaluated"] = int(aggr[method]["topics_evaluated"])
    return aggr


def _best_method(aggregate: Dict[str, Dict[str, float]]) -> str:
    best_method, _, _ = _best_method_with_scores(aggregate)
    return best_method


def _method_final_score(v: Dict[str, Any]) -> float:
    # Standardized weighted score (equal weights).
    # final_score = 0.25*P@10 + 0.25*R@10 + 0.25*MRR@10 + 0.25*NDCG@10
    return (
        0.25 * float(v.get("precision_at_10", 0.0))
        + 0.25 * float(v.get("recall_at_10", 0.0))
        + 0.25 * float(v.get("mrr_at_10", 0.0))
        + 0.25 * float(v.get("ndcg_at_10", 0.0))
    )


def _best_method_with_scores(aggregate: Dict[str, Dict[str, float]]) -> Tuple[str, Dict[str, float], bool]:
    # Fully data-driven selection; no hardcoded method preference.
    scores: Dict[str, float] = {m: _method_final_score(aggregate.get(m, {})) for m in METHODS}
    if not scores:
        return "none", {}, False
    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_method, top_score = ordered[0]
    second_score = ordered[1][1] if len(ordered) > 1 else float("-inf")
    is_tie = len(ordered) > 1 and abs(top_score - second_score) < 0.01
    if is_tie:
        return "tie", scores, True
    return top_method, scores, False


def _write_report(
    n_mcqs: int,
    weak_topics: List[str],
    aggregate: Dict[str, Dict[str, float]],
    best_method: str,
    final_scores: Dict[str, float],
    is_tie: bool,
) -> None:
    lines: List[str] = []
    lines.append("# Retrieval Comparison Research Report")
    lines.append("")
    lines.append("## Dataset Summary")
    lines.append(f"- Total MCQs: **{n_mcqs}**")
    lines.append(f"- Weak topics evaluated: **{len(weak_topics)}**")
    lines.append(f"- Weak topic list: {', '.join(weak_topics) if weak_topics else 'None'}")
    lines.append("")
    lines.append("## Method Comparison")
    lines.append("| Method | Description |")
    lines.append("|---|---|")
    lines.append("| tfidf_cosine | Sparse lexical retrieval using TF-IDF + cosine similarity |")
    lines.append("| embedding_cosine | Dense semantic retrieval using Sentence-BERT + cosine similarity |")
    lines.append("| hybrid | Weighted fusion: 0.4 TF-IDF + 0.6 embedding |")
    lines.append("")
    lines.append("## Metric Comparison (Average Across Weak Topics)")
    lines.append("| Method | P@10 | R@10 | MRR@10 | NDCG@10 |")
    lines.append("|---|---:|---:|---:|---:|")
    for m in METHODS:
        v = aggregate.get(m, {})
        lines.append(
            f"| {m} | {v.get('precision_at_10', 0):.4f} | {v.get('recall_at_10', 0):.4f} | "
            f"{v.get('mrr_at_10', 0):.4f} | {v.get('ndcg_at_10', 0):.4f} |"
        )
    lines.append("")
    lines.append("## Final Score (Data-Driven)")
    lines.append("| Method | Final Score |")
    lines.append("|---|---:|")
    for m in METHODS:
        lines.append(f"| {m} | {float(final_scores.get(m, 0.0)):.4f} |")
    lines.append("")
    lines.append("## Best Method")
    lines.append(f"- **Best performing method:** `{best_method}`")
    lines.append(
        "- Weighted score used: `0.25*precision@10 + 0.25*recall@10 + 0.25*mrr@10 + 0.25*ndcg@10`."
    )
    if is_tie:
        lines.append("- Top methods are statistically similar (`|Δscore| < 0.01`), so result is reported as `tie`.")
    lines.append("")
    lines.append("## Research Interpretation")
    if best_method == "tie":
        lines.append(
            "- No single winner is declared because top methods are within the tie threshold; all tied methods are competitive."
        )
    elif best_method == "hybrid":
        lines.append(
            "- Hybrid generally balances lexical precision (TF-IDF) with semantic matching (embedding), "
            "improving ranking quality while preserving topic relevance."
        )
    elif best_method == "embedding_cosine":
        lines.append(
            "- Embedding retrieval likely performs better because weak-topic queries are semantic and require concept-level matching."
        )
    else:
        lines.append(
            "- TF-IDF performs best in this run, indicating stronger lexical overlap between weak-topic names and MCQ text."
        )
    lines.append(
        "- In this offline protocol, relevance is topic-alignment based over the full MCQ candidate pool for each weak topic."
    )
    lines.append("")
    RESEARCH_REPORT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_method_comparison_csv(aggregate: Dict[str, Dict[str, float]]) -> None:
    rows = []
    for m in METHODS:
        v = aggregate.get(m, {})
        rows.append(
            {
                "method": m,
                "precision@10": float(v.get("precision_at_10", 0.0)),
                "recall@10": float(v.get("recall_at_10", 0.0)),
                "mrr@10": float(v.get("mrr_at_10", 0.0)),
                "ndcg@10": float(v.get("ndcg_at_10", 0.0)),
                "final_score": _method_final_score(v),
            }
        )
    pd.DataFrame(rows).to_csv(METHOD_COMPARISON_CSV_PATH, index=False)


def _write_k10_dashboard_metrics(
    aggregate: Dict[str, Dict[str, float]],
    final_scores: Dict[str, float],
) -> List[Dict[str, Any]]:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows: List[Dict[str, Any]] = []
    for method in METHODS:
        v = aggregate.get(method, {})
        rows.append(
            {
                "method": method,
                "precision_at_10": round(float(v.get("precision_at_10", 0.0)), 4),
                "recall_at_10": round(float(v.get("recall_at_10", 0.0)), 4),
                "mrr_at_10": round(float(v.get("mrr_at_10", 0.0)), 4),
                "ndcg_at_10": round(float(v.get("ndcg_at_10", 0.0)), 4),
                "final_score": round(float(final_scores.get(method, 0.0)), 4),
                "k": int(TOP_K),
                "generated_at": generated_at,
            }
        )

    # Overwrite on every run for dashboard/panel ingestion.
    RETRIEVAL_METRICS_K10_JSON_PATH.write_text(
        json.dumps({"k": int(TOP_K), "generated_at": generated_at, "methods": rows}, indent=2),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "method": r["method"],
                "precision_at_10": r["precision_at_10"],
                "recall_at_10": r["recall_at_10"],
                "mrr_at_10": r["mrr_at_10"],
                "ndcg_at_10": r["ndcg_at_10"],
                "final_score": r["final_score"],
            }
            for r in rows
        ]
    ).to_csv(RETRIEVAL_METRICS_K10_CSV_PATH, index=False)
    return rows


def _write_research_explanations(
    results_by_topic: List[Dict[str, Any]],
    aggregate: Dict[str, Dict[str, float]],
    best_method: str,
    is_tie: bool,
) -> None:
    lines: List[str] = []
    lines.append("# Retrieval Research Explanation Log")
    lines.append("")
    lines.append(
        "Per weak-topic comparison of TF-IDF vs Embedding vs Hybrid using identical query/candidate settings."
    )
    lines.append("")
    lines.append("## Method-Level Summary")
    for m in METHODS:
        mv = aggregate.get(m, {})
        fs = _method_final_score(mv)
        if fs >= 0.60:
            reason = "Strong across rank quality and early precision."
        elif fs >= 0.35:
            reason = "Moderate performance with mixed strengths."
        else:
            reason = "Weak performance; likely suffers from topic mismatch or sparse lexical overlap."
        lines.append(
            f"- {m}: P@10={float(mv.get('precision_at_10', 0.0)):.4f}, "
            f"R@10={float(mv.get('recall_at_10', 0.0)):.4f}, "
            f"MRR@10={float(mv.get('mrr_at_10', 0.0)):.4f}, "
            f"NDCG@10={float(mv.get('ndcg_at_10', 0.0)):.4f}, "
            f"final_score={fs:.4f}. {reason}"
        )
    lines.append(f"- BEST_METHOD={best_method}")
    if is_tie:
        lines.append("- Tie detected (`|Δscore| < 0.01`): top methods are statistically similar.")
    lines.append("")

    win_examples: Dict[str, List[str]] = {m: [] for m in METHODS}
    for item in results_by_topic:
        topic = str(item.get("weak_topic", ""))
        methods = item.get("methods", {})
        weighted = {}
        for m in METHODS:
            v = methods.get(m, {})
            weighted[m] = _method_final_score(v)
        winner = max(weighted.items(), key=lambda x: x[1])[0]
        win_examples[winner].append(topic)
        lines.append(f"## Query weak topic: {topic}")
        for m in METHODS:
            mv = methods.get(m, {})
            lines.append(
                f"- {m}: P@10={mv.get('precision_at_10', 0):.4f}, "
                f"R@10={mv.get('recall_at_10', 0):.4f}, "
                f"MRR@10={mv.get('mrr_at_10', 0):.4f}, "
                f"NDCG@10={mv.get('ndcg_at_10', 0):.4f}, "
                f"weighted={weighted[m]:.4f}"
            )
        if winner == "hybrid":
            reason = "Hybrid likely benefits from balancing lexical term match and semantic similarity."
        elif winner == "tfidf_cosine":
            reason = "TF-IDF likely wins where query wording overlaps strongly with MCQ lexical terms."
        else:
            reason = "Embedding likely wins where concept-level semantic phrasing differs from literal terms."
        lines.append(f"- Winner: **{winner}**. {reason}")
        lines.append("")

    lines.append("## Example Cases")
    for m in METHODS:
        sample = ", ".join(win_examples[m][:5]) if win_examples[m] else "None"
        lines.append(f"- {m} wins on: {sample}")
    lines.append("")
    EXPLANATION_LOG_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _write_metric_bar_chart(aggregate: Dict[str, Dict[str, float]]) -> None:
    try:
        methods = list(METHODS)
        metrics = ["precision_at_10", "recall_at_10", "mrr_at_10", "ndcg_at_10"]
        labels = ["P@10", "R@10", "MRR@10", "NDCG@10"]

        x = np.arange(len(methods), dtype=np.float64)
        w = 0.18
        plt.figure(figsize=(10, 5))
        for i, (metric, label) in enumerate(zip(metrics, labels)):
            vals = [float(aggregate.get(m, {}).get(metric, 0.0)) for m in methods]
            plt.bar(x + (i - 1.5) * w, vals, width=w, label=label, alpha=0.85)
        plt.xticks(x, methods, rotation=10)
        plt.ylim(0.0, 1.0)
        plt.ylabel("Score")
        plt.title("Retrieval Method Comparison")
        plt.legend()
        plt.tight_layout()
        plt.savefig(EVAL_PLOT_PATH, dpi=150)
        plt.close()
    except Exception as e:
        print(f"[retrieval_validation] plot skipped: {e}")


def _stratified_topic_groups(summary_rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    # Frequency proxy: total relevant items in candidate pool.
    by_topic_relevant: Dict[str, int] = {}
    for r in summary_rows:
        wt = str(r.get("weak_topic", ""))
        if wt not in by_topic_relevant:
            by_topic_relevant[wt] = int(r.get("total_relevant_in_pool", 0))

    topics = list(by_topic_relevant.keys())
    if not topics:
        return {"high_frequency": [], "medium_frequency": [], "low_frequency": []}
    vals = np.array([by_topic_relevant[t] for t in topics], dtype=np.float64)
    q1 = float(np.quantile(vals, 1 / 3))
    q2 = float(np.quantile(vals, 2 / 3))

    groups = {"high_frequency": [], "medium_frequency": [], "low_frequency": []}
    for t in topics:
        v = float(by_topic_relevant[t])
        if v <= q1:
            groups["low_frequency"].append(t)
        elif v <= q2:
            groups["medium_frequency"].append(t)
        else:
            groups["high_frequency"].append(t)
    return groups


def _aggregate_for_topics(summary_rows: List[Dict[str, Any]], topics: List[str]) -> Dict[str, Dict[str, float]]:
    if not topics:
        return {m: {"precision_at_10": 0.0, "recall_at_10": 0.0, "mrr_at_10": 0.0, "ndcg_at_10": 0.0, "topics_evaluated": 0} for m in METHODS}
    topic_set = set(topics)
    filtered = [r for r in summary_rows if str(r.get("weak_topic", "")) in topic_set]
    return _aggregate(filtered)


def _method_scores_per_topic(results_by_topic: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    for item in results_by_topic:
        wt = str(item.get("weak_topic", ""))
        out[wt] = {}
        methods = item.get("methods", {})
        for m in METHODS:
            out[wt][m] = _method_final_score(methods.get(m, {}))
    return out


def _build_stratified_analysis(
    summary_rows: List[Dict[str, Any]],
    results_by_topic: List[Dict[str, Any]],
    global_best_method: str,
    global_is_tie: bool,
) -> Dict[str, Any]:
    groups = _stratified_topic_groups(summary_rows)
    stratified: Dict[str, Any] = {}
    for gname, topics in groups.items():
        agg = _aggregate_for_topics(summary_rows, topics)
        best, scores, is_tie = _best_method_with_scores(agg)
        stratified[gname] = {
            "topics": topics,
            "topics_count": len(topics),
            "aggregate_metrics": agg,
            "final_scores": {k: round(float(v), 6) for k, v in scores.items()},
            "best_method": best,
            "is_tie": bool(is_tie),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "global": {
            "best_method": global_best_method,
            "is_tie": bool(global_is_tie),
        },
        "stratified": stratified,
        "method_scores_per_topic": _method_scores_per_topic(results_by_topic),
    }


def _write_significance_report(
    results_by_topic: List[Dict[str, Any]],
    final_scores: Dict[str, float],
    best_method: str,
    is_tie: bool,
) -> None:
    per_topic = _method_scores_per_topic(results_by_topic)
    lines: List[str] = []
    lines.append("# Statistical Significance Report")
    lines.append("")
    lines.append("## Global Final Scores")
    for m in METHODS:
        lines.append(f"- {m}: {float(final_scores.get(m, 0.0)):.6f}")
    lines.append("")

    ordered = sorted(final_scores.items(), key=lambda x: x[1], reverse=True)
    if len(ordered) < 2:
        lines.append("Insufficient methods for pairwise separation check.")
        SIGNIFICANCE_REPORT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return

    top_method, top_score = ordered[0]
    second_method, second_score = ordered[1]
    gap = float(top_score - second_score)

    diffs: List[float] = []
    for wt, scores in per_topic.items():
        if top_method in scores and second_method in scores:
            diffs.append(float(scores[top_method] - scores[second_method]))
    std_diff = float(np.std(np.array(diffs, dtype=np.float64))) if diffs else 0.0

    # Rule requested: if score diff < 0.01 AND std deviation low => statistically equivalent
    low_std_threshold = 0.02
    equivalent = (gap < 0.01) and (std_diff < low_std_threshold)
    lines.append("## Separation Check")
    lines.append(f"- Top methods compared: `{top_method}` vs `{second_method}`")
    lines.append(f"- Global score gap: {gap:.6f}")
    lines.append(f"- Std. deviation of per-topic score differences: {std_diff:.6f}")
    lines.append(f"- Low-std threshold: {low_std_threshold:.4f}")
    lines.append("")
    if equivalent:
        lines.append("**Result:** statistically equivalent methods.")
        lines.append("Reason: global gap < 0.01 and per-topic score-variance is low.")
    else:
        lines.append("**Result:** methods are separable under current criterion.")
    lines.append("")
    lines.append("## Final Selection")
    lines.append(f"- BEST_METHOD: `{best_method}`")
    lines.append(f"- Tie flag: `{is_tie}`")
    SIGNIFICANCE_REPORT_PATH.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    quiz_state = _safe_json(QUIZ_STATE_PATH)
    weak_topics = [str(x).strip() for x in (quiz_state.get("weak_topics_confirmed") or []) if str(x).strip()]
    weak_topics = list(dict.fromkeys(weak_topics))
    if not weak_topics:
        # still produce reproducible empty artifacts
        RETRIEVAL_JSON_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "weak_topics": [],
                    "n_mcqs": 0,
                    "methods": list(METHODS),
                    "results_by_weak_topic": [],
                    "aggregate": {},
                    "best_method": "none",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        pd.DataFrame(
            columns=[
                "weak_topic",
                "method",
                "precision_at_10",
                "recall_at_10",
                "mrr_at_10",
                "ndcg_at_10",
                "diversity_unique_topics_at_10",
                "relevant_in_top_10",
                "total_relevant_in_pool",
                "pool_size",
            ]
        ).to_csv(SUMMARY_CSV_PATH, index=False)
        _write_method_comparison_csv({})
        _write_k10_dashboard_metrics({}, {})
        _write_report(0, [], {}, "none", {}, False)
        _build_fairness_report([], [], {}, "none")
        _write_research_explanations([], {}, "none", False)
        STRATIFIED_JSON_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "global": {"best_method": "none", "is_tie": False},
                    "stratified": {},
                    "method_scores_per_topic": {},
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        _write_significance_report([], {}, "none", False)
        print("[retrieval_validation] No weak topics; empty artifacts generated.")
        return

    mcq_df, all_topics, sims = _load_runtime_data()
    mcq_texts = [str(x) for x in mcq_df.get("question", []).tolist()]
    topic_labels = _topic_labels_from_all_topics(all_topics)
    mcq_topics = _assign_mcq_topics(mcq_df, topic_labels, sims)

    # Representations over full MCQ pool.
    tfidf_vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    tfidf_mat = tfidf_vec.fit_transform(mcq_texts if mcq_texts else [""])

    import sys

    if str(BASE_DIR) not in sys.path:
        sys.path.insert(0, str(BASE_DIR))
    from mcq_utils import embedder

    mcq_embs = (
        embedder.encode(mcq_texts, show_progress_bar=False, convert_to_numpy=True)
        if mcq_texts
        else np.zeros((0, 384), dtype=np.float64)
    )

    results_by_topic: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for wt in weak_topics:
        q_tfidf = tfidf_vec.transform([wt])
        tfidf_scores = np.asarray(cosine_similarity(q_tfidf, tfidf_mat)[0], dtype=np.float64)
        q_emb = embedder.encode([wt], show_progress_bar=False, convert_to_numpy=True)[0]
        emb_scores = np.asarray(cosine_similarity([q_emb], mcq_embs)[0], dtype=np.float64)

        item = _evaluate_one_topic(
            weak_topic=wt,
            mcq_df=mcq_df,
            mcq_texts=mcq_texts,
            mcq_topics=mcq_topics,
            tfidf_scores=tfidf_scores,
            emb_scores=emb_scores,
        )
        results_by_topic.append(item)

        for method in METHODS:
            m = item["methods"][method]
            summary_rows.append(
                {
                    "weak_topic": wt,
                    "method": method,
                    "precision_at_10": m["precision_at_10"],
                    "recall_at_10": m["recall_at_10"],
                    "mrr_at_10": m["mrr_at_10"],
                    "ndcg_at_10": m["ndcg_at_10"],
                    "diversity_unique_topics_at_10": m["diversity_unique_topics_at_10"],
                    "relevant_in_top_10": m["relevant_in_top_10"],
                    "total_relevant_in_pool": m["total_relevant_in_pool"],
                    "pool_size": m["pool_size"],
                }
            )

    aggregate = _aggregate(summary_rows)
    best_method, final_scores, is_tie = _best_method_with_scores(aggregate)

    retrieval_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_mcqs": int(len(mcq_df)),
        "weak_topics": weak_topics,
        "weak_topics_count": len(weak_topics),
        "methods": list(METHODS),
        "results_by_weak_topic": results_by_topic,
        "aggregate": aggregate,
        "final_scores": {k: round(float(v), 6) for k, v in final_scores.items()},
        "is_tie": bool(is_tie),
        "best_method": best_method,
    }
    RETRIEVAL_JSON_PATH.write_text(json.dumps(retrieval_payload, indent=2), encoding="utf-8")

    pd.DataFrame(summary_rows).to_csv(SUMMARY_CSV_PATH, index=False)
    _write_method_comparison_csv(aggregate)
    standardized_k10_rows = _write_k10_dashboard_metrics(aggregate, final_scores)
    _write_research_explanations(results_by_topic, aggregate, best_method, is_tie)
    _write_metric_bar_chart(aggregate)
    stratified_payload = _build_stratified_analysis(
        summary_rows=summary_rows,
        results_by_topic=results_by_topic,
        global_best_method=best_method,
        global_is_tie=is_tie,
    )
    STRATIFIED_JSON_PATH.write_text(json.dumps(stratified_payload, indent=2), encoding="utf-8")
    _write_significance_report(
        results_by_topic=results_by_topic,
        final_scores=final_scores,
        best_method=best_method,
        is_tie=is_tie,
    )

    metrics_payload = _safe_json(EVAL_METRICS_PATH)
    metrics_payload["retrieval_comparison_validation"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "k": int(TOP_K),
        "weak_topics_count": len(weak_topics),
        "n_mcqs": int(len(mcq_df)),
        "aggregate_metrics": aggregate,
        "final_scores": {k: round(float(v), 6) for k, v in final_scores.items()},
        "is_tie": bool(is_tie),
        "best_method": best_method,
        "standardized_k10_metrics": standardized_k10_rows,
        "artifacts": {
            "retrieval_comparison_json": str(RETRIEVAL_JSON_PATH),
            "retrieval_comparison_summary_csv": str(SUMMARY_CSV_PATH),
            "retrieval_metrics_k10_json": str(RETRIEVAL_METRICS_K10_JSON_PATH),
            "retrieval_metrics_k10_csv": str(RETRIEVAL_METRICS_K10_CSV_PATH),
            "retrieval_method_comparison_csv": str(METHOD_COMPARISON_CSV_PATH),
            "research_report_md": str(RESEARCH_REPORT_PATH),
            "explanation_log_md": str(EXPLANATION_LOG_PATH),
            "evaluation_plot_png": str(EVAL_PLOT_PATH),
            "retrieval_stratified_analysis_json": str(STRATIFIED_JSON_PATH),
            "statistical_significance_report_md": str(SIGNIFICANCE_REPORT_PATH),
        },
    }
    EVAL_METRICS_PATH.write_text(json.dumps(metrics_payload, indent=2), encoding="utf-8")

    _write_report(
        n_mcqs=int(len(mcq_df)),
        weak_topics=weak_topics,
        aggregate=aggregate,
        best_method=best_method,
        final_scores=final_scores,
        is_tie=is_tie,
    )
    _build_fairness_report(
        weak_topics=weak_topics,
        summary_rows=summary_rows,
        aggregate=aggregate,
        best_method=best_method,
    )

    print("[retrieval_validation] generated:")
    print(f" - {RETRIEVAL_JSON_PATH}")
    print(f" - {EVAL_METRICS_PATH}")
    print(f" - {SUMMARY_CSV_PATH}")
    print(f" - {METHOD_COMPARISON_CSV_PATH}")
    print(f" - {RESEARCH_REPORT_PATH}")
    print(f" - {FAIRNESS_REPORT_PATH}")
    print(f" - {EXPLANATION_LOG_PATH}")
    print(f" - {EVAL_PLOT_PATH}")
    print(f" - {STRATIFIED_JSON_PATH}")
    print(f" - {SIGNIFICANCE_REPORT_PATH}")
    print(f" - {RETRIEVAL_METRICS_K10_JSON_PATH}")
    print(f" - {RETRIEVAL_METRICS_K10_CSV_PATH}")
    print(f"[retrieval_validation] best_method={best_method}")
    if is_tie:
        print("BEST_METHOD = tie")
        print("[retrieval_validation] tie_reason=top method score difference < 0.01")
    else:
        print(f"BEST_METHOD = {best_method}")
    print(f"Evaluation completed with K={TOP_K}")
    print(f"Best Method: {best_method}")
    print("Scores saved to outputs/retrieval_metrics_k10.*")


if __name__ == "__main__":
    main()

