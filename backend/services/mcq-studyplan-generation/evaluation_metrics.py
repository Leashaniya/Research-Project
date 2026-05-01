"""Evaluation metrics for recommendation and adaptive planning quality."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

import pandas as pd

from topic_labels import clean_topic_display_name

OUTPUT_PATH = Path("outputs") / "evaluation_metrics.json"
RECOMMENDATIONS_PATH = Path("outputs") / "graphrag_recommendations.json"
QUIZ_STATE_PATH = Path("outputs") / "graphrag_quiz_state.json"


def _norm_topic(value: Any) -> str:
    if value is None:
        return ""
    s = clean_topic_display_name(str(value).strip())
    return s.strip().lower()


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _topic_match(a: str, b: str) -> bool:
    """Case-insensitive partial match for topic labels."""
    a_n = _norm_topic(a)
    b_n = _norm_topic(b)
    if not a_n or not b_n:
        return False
    return a_n == b_n or (a_n in b_n) or (b_n in a_n)


def _is_clean_precision_topic(label: str) -> bool:
    raw = str(label or "").strip()
    if not raw:
        return False
    if raw.count(",") > 2:
        return False
    if len(raw) > 40:
        return False
    low = raw.lower()
    blocked = ("score", "lecture", "quiz", "lower")
    return not any(tok in low for tok in blocked)


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    text = ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, json.JSONDecodeError):
        return {}
    if not text.strip():
        return {}

    # Fast path for valid single-object JSON.
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    # Recovery path: tolerate concatenated JSON objects by decoding sequentially.
    # Keep the dict with the richest recommendation payload.
    decoder = json.JSONDecoder()
    i = 0
    n = len(text)
    recovered: List[Dict[str, Any]] = []
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        try:
            obj, end = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        if isinstance(obj, dict):
            recovered.append(obj)
        i = end

    if not recovered:
        print(f"[evaluation_metrics] warning: could not decode JSON from {path}")
        return {}

    def _score(d: Dict[str, Any]) -> int:
        recs = d.get("recommendations")
        if isinstance(recs, list):
            return len(recs)
        return 0

    best = max(recovered, key=_score)
    if len(recovered) > 1:
        print(
            f"[evaluation_metrics] warning: recovered {len(recovered)} concatenated JSON object(s) from {path}; using best payload"
        )
    return best


def _recommended_topics_from_rows(recommendations: List[Dict[str, Any]]) -> List[str]:
    ranked_topics: List[str] = []
    for rec in recommendations:
        trace = rec.get("reason_trace") or {}
        candidates: List[str] = []
        if trace.get("supports_weak_topic"):
            candidates.append(_norm_topic(trace.get("supports_weak_topic")))
        if trace.get("related_concept"):
            candidates.append(_norm_topic(trace.get("related_concept")))
        for path in (trace.get("prerequisite_path") or []):
            raw = str(path)
            if "→" in raw:
                _, right = raw.split("→", 1)
                candidates.append(_norm_topic(right))
        if rec.get("recommended_topic"):
            candidates.append(_norm_topic(rec.get("recommended_topic")))
        # Extra fallbacks in case topic label is stored with other names.
        for key in ("topic", "topic_label", "mapped_topic", "topic_name"):
            if rec.get(key):
                candidates.append(_norm_topic(rec.get(key)))
        # Parse textual reasons when structured fields are missing.
        for reason in rec.get("reasons") or []:
            r = str(reason)
            if ":" in r:
                _, right = r.split(":", 1)
                candidates.append(_norm_topic(right))
        for c in candidates:
            if c and _is_clean_precision_topic(c):
                ranked_topics.append(c)
            elif c:
                print(f"[evaluation_metrics] skipping noisy recommended topic label: '{c}'")
    return _dedupe_keep_order(ranked_topics)


def _precision_at_k(pred_topics: List[str], weak_truth: Set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = pred_topics[:k]
    if not top_k:
        print(f"[evaluation_metrics] precision@{k}: no predicted topics")
        return 0.0
    weak_list = list(weak_truth)
    comparisons = []
    hits = 0
    for rec_t in top_k:
        rec_hit = False
        per_weak = []
        for weak_t in weak_list:
            is_match = _topic_match(rec_t, weak_t)
            per_weak.append((weak_t, is_match))
            if is_match:
                rec_hit = True
        comparisons.append((rec_t, rec_hit, per_weak))
        if rec_hit:
            hits += 1
    print(
        f"[evaluation_metrics] precision@{k} comparisons summary: "
        f"{[(c[0], c[1]) for c in comparisons]}"
    )
    return round(hits / len(top_k), 4)


def _topic_coverage_score(
    percentage_df: Optional[pd.DataFrame],
    adaptive_plan_df: Optional[pd.DataFrame],
) -> float:
    if percentage_df is None or percentage_df.empty:
        return 0.0
    if adaptive_plan_df is None or adaptive_plan_df.empty:
        return 0.0

    pct_col = "Percentage_of_Total" if "Percentage_of_Total" in percentage_df.columns else "Percentage"
    if pct_col not in percentage_df.columns or "Lecture_File" not in percentage_df.columns:
        return 0.0

    freq_sorted = percentage_df.sort_values(pct_col, ascending=False).copy()
    top_n = min(5, len(freq_sorted))
    top_frequency_topics = {_norm_topic(v) for v in freq_sorted.head(top_n)["Lecture_File"].tolist()}
    if not top_frequency_topics:
        return 0.0

    hours_col = "Adaptive_Hours" if "Adaptive_Hours" in adaptive_plan_df.columns else "Recommended_Hours"
    if hours_col not in adaptive_plan_df.columns or "Lecture" not in adaptive_plan_df.columns:
        return 0.0

    total_hours = 0.0
    covered_hours = 0.0
    for _, row in adaptive_plan_df.iterrows():
        lecture = _norm_topic(row.get("Lecture"))
        hours = float(row.get(hours_col, 0) or 0)
        total_hours += hours
        if lecture in top_frequency_topics:
            covered_hours += hours
    if total_hours <= 0:
        return 0.0
    return round(covered_hours / total_hours, 4)


def _recommendation_diversity(pred_topics: List[str], recommendations: List[Dict[str, Any]]) -> float:
    if not recommendations:
        print("[evaluation_metrics] warning: recommendations list is empty; diversity=0.0")
        return 0.0
    if not pred_topics:
        print("[evaluation_metrics] warning: no recommendation topic labels found; diversity=0.0")
        return 0.0
    return round(len(set(pred_topics)) / max(1, len(recommendations)), 4)


def compute_evaluation_metrics(
    quiz_results: Optional[Dict[str, Any]] = None,
    recommendations_payload: Optional[Dict[str, Any]] = None,
    percentage_df: Optional[pd.DataFrame] = None,
    adaptive_plan_df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    quiz_results = quiz_results or _load_json(QUIZ_STATE_PATH)
    recommendations_payload = recommendations_payload or _load_json(RECOMMENDATIONS_PATH)
    recommendations = recommendations_payload.get("recommendations") or []

    weak_topics_confirmed = quiz_results.get("weak_topics_confirmed") or []
    if not weak_topics_confirmed:
        # Requested fallback: try quiz state file even when runtime payload is present.
        quiz_fallback = _load_json(QUIZ_STATE_PATH)
        weak_topics_confirmed = quiz_fallback.get("weak_topics_confirmed") or []
        if weak_topics_confirmed:
            print("[evaluation_metrics] fallback loaded weak_topics_confirmed from graphrag_quiz_state.json")

    if not recommendations:
        # Requested fallback: load persisted recommendations if runtime payload is empty.
        rec_fallback = _load_json(RECOMMENDATIONS_PATH)
        recommendations = rec_fallback.get("recommendations") or []
        recommendations_payload = rec_fallback or recommendations_payload
        if recommendations:
            print("[evaluation_metrics] fallback loaded recommendations from graphrag_recommendations.json")

    weak_truth = {_norm_topic(t) for t in weak_topics_confirmed if _norm_topic(t)}
    pred_topics = _recommended_topics_from_rows(recommendations)
    top_recommended_for_debug = pred_topics[:5]

    print(f"[evaluation_metrics] weak_topics_confirmed(raw): {weak_topics_confirmed}")
    print(f"[evaluation_metrics] weak_topics_confirmed(normalized): {sorted(weak_truth)}")
    print(f"[evaluation_metrics] recommended_topics_top5(normalized): {top_recommended_for_debug}")
    print(f"[evaluation_metrics] recommendations_count: {len(recommendations)}")

    metrics = {
        "precision_at_3": _precision_at_k(pred_topics, weak_truth, 3),
        "precision_at_5": _precision_at_k(pred_topics, weak_truth, 5),
        "topic_coverage_score": _topic_coverage_score(percentage_df, adaptive_plan_df),
        "recommendation_diversity": _recommendation_diversity(pred_topics, recommendations),
    }
    print(f"[evaluation_metrics] final metrics: {metrics}")
    return metrics


def save_evaluation_metrics(metrics: Dict[str, float], path: Path = OUTPUT_PATH) -> None:
    payload = dict(metrics)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass


def calculate_and_save_evaluation_metrics(
    quiz_results: Optional[Dict[str, Any]] = None,
    recommendations_payload: Optional[Dict[str, Any]] = None,
    percentage_df: Optional[pd.DataFrame] = None,
    adaptive_plan_df: Optional[pd.DataFrame] = None,
) -> Dict[str, float]:
    metrics = compute_evaluation_metrics(
        quiz_results=quiz_results,
        recommendations_payload=recommendations_payload,
        percentage_df=percentage_df,
        adaptive_plan_df=adaptive_plan_df,
    )
    save_evaluation_metrics(metrics)
    return metrics
