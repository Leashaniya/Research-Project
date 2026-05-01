"""
Retrieve and score dataset MCQs for GraphRAG-style recommendations.
Uses confirmed weak topics (quiz), lecture priority (exam-frequency proxy), topic–topic
relationships (similarity + keyword overlap), and topic–question similarity.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from analysis_utils import (
    classify_quiz_accuracy_band,
    lecture_mcq_share_dataframe,
)
from learning_state import get_learning_state
from quiz_extraction import NUM_TOP_PRIORITY_LECTURES
from topic_labels import clean_topic_display_name

# Default path: cwd is service root when FastAPI runs
DEFAULT_QUIZ_STATE_PATH = Path("outputs") / "graphrag_quiz_state.json"
DEFAULT_RECOMMENDATIONS_PATH = Path("outputs") / "graphrag_recommendations.json"
DEFAULT_STUDENT_HISTORY_PATH = Path("outputs") / "graphrag_student_history.json"

TFIDF_WEIGHT = 0.4
EMBED_WEIGHT = 0.6
USE_HYBRID_SCORING_DEFAULT = True

_TFIDF_CACHE: Dict[str, Any] = {
    "signature": None,
    "vectorizer": None,
    "matrix": None,
    "texts": None,
}

DBMS_PREREQUISITES: Dict[str, List[str]] = {
    "normalization": ["functional dependency", "relational algebra"],
    "sql joins": ["relational algebra", "set theory"],
    "transactions": ["concurrency control", "acid properties"],
    "indexing": ["file organization", "b-trees"],
    "query optimization": ["sql", "relational algebra"],
    "er diagram": ["entity", "relationship", "keys"],
    "concurrency control": ["transactions", "locking"],
}

DBMS_QUERY_SYNONYMS: Dict[str, List[str]] = {
    "join": ["sql joins", "inner join", "outer join", "relational algebra"],
    "normalization": ["1nf", "2nf", "3nf", "functional dependency"],
    "jdbc": ["database connectivity", "driver manager", "sql connection"],
    "transactions": ["acid properties", "concurrency control", "locking"],
    "indexing": ["b tree", "file organization", "query optimization"],
    "keys": ["primary key", "foreign key", "constraints"],
}


def load_quiz_state(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    p = path or DEFAULT_QUIZ_STATE_PATH
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _load_student_history(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or DEFAULT_STUDENT_HISTORY_PATH
    if not p.exists():
        return {"attempted_question_ids": [], "recommended_question_ids": []}
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}
        return {
            "attempted_question_ids": list(raw.get("attempted_question_ids") or []),
            "recommended_question_ids": list(raw.get("recommended_question_ids") or []),
        }
    except (json.JSONDecodeError, OSError):
        return {"attempted_question_ids": [], "recommended_question_ids": []}


def _save_student_history(history: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or DEFAULT_STUDENT_HISTORY_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except OSError:
        pass


def record_attempted_question_ids(question_ids: List[str], path: Optional[Path] = None) -> None:
    """Append attempted question IDs so future recommendations can avoid repeats."""
    if not question_ids:
        return
    history = _load_student_history(path=path)
    attempted = list(dict.fromkeys((history.get("attempted_question_ids") or []) + [str(q) for q in question_ids if str(q)]))
    history["attempted_question_ids"] = attempted[-1000:]
    history["recommended_question_ids"] = list(dict.fromkeys(history.get("recommended_question_ids") or []))[-500:]
    _save_student_history(history, path=path)


def _lecture_stem(name: str) -> str:
    base = os.path.basename(name or "")
    return base.replace(".pdf", "").replace(".PDF", "").strip()


def lecture_accuracy_map(
    quiz_state: Optional[Dict[str, Any]],
    lecture_data: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Map lecture basename (with .pdf) -> accuracy in 0..100. Uses topic_wise keys (question_id prefix)."""
    out: Dict[str, float] = {}
    if not quiz_state:
        return out
    tw = quiz_state.get("topic_wise") or {}
    for lec in lecture_data:
        fname = os.path.basename(lec.get("file", ""))
        stem = _lecture_stem(fname)
        acc = None
        if stem in tw and tw[stem].get("total", 0) > 0:
            acc = float(tw[stem].get("accuracy", 0))
        if acc is None and fname.replace(".pdf", "") in tw:
            k = fname.replace(".pdf", "")
            if tw[k].get("total", 0) > 0:
                acc = float(tw[k].get("accuracy", 0))
        if acc is not None:
            out[fname] = acc
            out.setdefault(stem, acc)
    return out


def topics_in_sims_order(lecture_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Same topic order as mcq_service + compute_similarities(all_topics, mcq_df)."""
    ordered = []
    for lecture in lecture_data:
        lid = lecture["id"]
        lfile = os.path.basename(lecture.get("file", ""))
        for topic in lecture.get("topics", []):
            ordered.append(
                {
                    "topic": topic,
                    "lecture_id": lid,
                    "lecture_file": lfile,
                }
            )
    return ordered


def priority_lecture_files_from_distribution(
    lecture_data: List[Dict[str, Any]],
    mcq_df: pd.DataFrame,
    sims: np.ndarray,
    top_n: int = 4,
) -> Tuple[pd.DataFrame, Set[str]]:
    """
    Priority = high share of dataset MCQs (exam-frequency proxy).
    Returns (priority_df, set of Lecture_File basenames in top_n).
    """
    dist = lecture_mcq_share_dataframe(lecture_data, mcq_df, sims)
    top_files: Set[str] = set()
    if not dist.empty and "Lecture_File" in dist.columns:
        for _, row in dist.head(top_n).iterrows():
            top_files.add(str(row["Lecture_File"]))
    return dist, top_files


def _display_label_for_topic_row(item: Dict[str, Any]) -> str:
    t = item["topic"]
    kws = t.get("keywords") or []
    if kws:
        return clean_topic_display_name(", ".join(str(k) for k in kws[:5]))
    return "Topic"


def _topic_matches_weak_label(topic: Dict[str, Any], weak_label: str) -> bool:
    wn = (weak_label or "").strip().lower()
    if not wn:
        return False
    kws = [str(k).lower() for k in topic.get("keywords", []) if k]
    blob = " ".join(kws)
    if wn in blob or (blob and len(blob) <= 40 and blob in wn):
        return True
    for k in kws:
        if len(k) >= 3 and (k in wn or wn in k):
            return True
    return False


def _norm_concept_key(raw: str) -> str:
    return " ".join((raw or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _topic_matches_concept(topic: Dict[str, Any], concept: str) -> bool:
    cn = _norm_concept_key(concept)
    if not cn:
        return False
    kws = [_norm_concept_key(str(k)) for k in topic.get("keywords", []) if str(k).strip()]
    blob = " ".join(kws)
    if cn in blob or (blob and blob in cn):
        return True
    for k in kws:
        if len(k) >= 3 and (k in cn or cn in k):
            return True
    return False


def _labels_match_partial(a: str, b: str) -> bool:
    """Partial/substring concept matching after topic display cleanup."""
    a_n = _norm_concept_key(clean_topic_display_name(a or ""))
    b_n = _norm_concept_key(clean_topic_display_name(b or ""))
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


def _question_text(row: pd.Series) -> str:
    q = str(row.get("question", "") or "").strip()
    opts = str(row.get("options", "") or "").strip()
    return f"{q} {opts}".strip()


def _norm_text_key(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _estimate_difficulty_level(row: pd.Series, blended_score: float) -> str:
    qtext = str(row.get("question", "") or "")
    opt_text = str(row.get("options", "") or "")
    token_count = len((qtext + " " + opt_text).split())
    if blended_score >= 78 or token_count <= 18:
        return "Easy"
    if blended_score >= 55 or token_count <= 40:
        return "Medium"
    return "Hard"


def _expand_query_terms(
    weak_names_cleaned: List[str],
    related_pairs: List[Dict[str, str]],
    prereq_pairs: List[Dict[str, str]],
    priority_files: Set[str],
) -> Dict[str, Any]:
    base_terms = [_norm_text_key(w) for w in weak_names_cleaned if _norm_text_key(w)]
    graph_neighbor_terms: List[str] = []
    for p in (related_pairs or []):
        rc = _norm_text_key(str((p or {}).get("related_concept", "")).strip())
        if rc:
            graph_neighbor_terms.append(rc)
    for p in (prereq_pairs or []):
        pc = _norm_text_key(
            str((p or {}).get("prerequisite_concept") or (p or {}).get("related_concept") or "").strip()
        )
        if pc:
            graph_neighbor_terms.append(pc)
    lecture_context_terms = [_norm_text_key(_lecture_stem(f)) for f in sorted(priority_files) if _norm_text_key(_lecture_stem(f))]

    synonym_terms: List[str] = []
    for term in base_terms:
        for k, vals in DBMS_QUERY_SYNONYMS.items():
            nk = _norm_text_key(k)
            if term == nk or term in nk or nk in term:
                synonym_terms.extend([_norm_text_key(v) for v in vals if _norm_text_key(v)])

    expanded_terms = list(dict.fromkeys(base_terms + synonym_terms + graph_neighbor_terms + lecture_context_terms))
    query_text = " ".join(expanded_terms).strip() or "database management system"
    return {
        "base_terms": base_terms,
        "synonym_terms": list(dict.fromkeys(synonym_terms)),
        "graph_neighbor_terms": list(dict.fromkeys(graph_neighbor_terms)),
        "lecture_context_terms": list(dict.fromkeys(lecture_context_terms)),
        "expanded_terms": expanded_terms,
        "query_text": query_text,
    }


def query_understanding_layer(
    raw_query: str,
    weak_topics: List[str],
    related_pairs: List[Dict[str, str]],
    prereq_pairs: List[Dict[str, str]],
    priority_files: Set[str],
) -> Dict[str, Any]:
    # Layer 1: query understanding only (no retrieval).
    seed = [raw_query] + list(weak_topics or [])
    seed = [s for s in seed if str(s).strip()]
    ctx = _expand_query_terms(
        weak_names_cleaned=seed,
        related_pairs=related_pairs,
        prereq_pairs=prereq_pairs,
        priority_files=priority_files,
    )
    ctx["raw_query"] = raw_query
    return ctx


def candidate_retrieval_layer(
    expanded_query: Dict[str, Any],
    mcq_df: pd.DataFrame,
    top_k: int,
    multiplier: int = 12,
) -> Dict[str, Any]:
    # Layer 2: retrieve wide candidate pool from expanded query, no ranking fusion here.
    query_text = str((expanded_query or {}).get("query_text") or "").strip() or "database management system"
    vectorizer, tfidf_matrix, _ = _ensure_tfidf_cache(mcq_df)
    q_vec = vectorizer.transform([query_text])
    tfidf_scores = cosine_similarity(q_vec, tfidf_matrix).flatten()
    candidate_size = min(len(mcq_df), max(top_k * multiplier, top_k * 2))
    candidate_idx = np.argsort(tfidf_scores)[::-1][:candidate_size]
    return {
        "candidate_indices": candidate_idx.tolist(),
        "tfidf_scores": tfidf_scores,
        "candidate_size": int(candidate_size),
    }


def ranking_layer(
    rec_rows: List[Dict[str, Any]],
    tfidf_scores: np.ndarray,
    embedding_signal_vec: np.ndarray,
    use_hybrid_scoring: bool,
) -> List[Dict[str, Any]]:
    # Layer 3: multi-signal ranking only.
    hybrid_scores = compute_hybrid_scores(
        query_text="",
        tfidf_scores=tfidf_scores,
        embedding_scores=embedding_signal_vec,
        tfidf_weight=TFIDF_WEIGHT,
        embed_weight=EMBED_WEIGHT,
    )
    ranked_rows: List[Dict[str, Any]] = []
    for rec in rec_rows:
        ridx = int(rec.get("row_index", -1))
        tfidf_v = float(tfidf_scores[ridx]) if 0 <= ridx < len(tfidf_scores) else 0.0
        embed_v = float(embedding_signal_vec[ridx]) if 0 <= ridx < len(embedding_signal_vec) else 0.0
        hybrid_v = float(hybrid_scores[ridx]) if 0 <= ridx < len(hybrid_scores) else 0.0
        soft_weak_boost = 0.03 if rec.get("_weak_topic_boosted", False) else 0.0
        rec["tfidf_score"] = round(tfidf_v, 6)
        rec["embedding_score"] = round(embed_v, 6)
        rec["hybrid_score"] = round(hybrid_v + soft_weak_boost, 6)
        rec["ranking_explanation"] = {
            "contribution": {
                "lexical_tfidf": round(tfidf_v, 6),
                "semantic_embedding": round(embed_v, 6),
                "soft_weak_boost": round(soft_weak_boost, 6),
                "hybrid_used": bool(use_hybrid_scoring),
            },
            "confidence": "high" if hybrid_v >= 0.7 else ("medium" if hybrid_v >= 0.45 else "low"),
        }
        ranked_rows.append(rec)
    ranked_rows.sort(
        key=lambda x: x["hybrid_score"] if use_hybrid_scoring else x["score"],
        reverse=True,
    )
    return ranked_rows


def _mmr_rerank(
    rows: List[Dict[str, Any]],
    mcq_df: pd.DataFrame,
    tfidf_matrix: Any,
    lambda_mult: float = 0.75,
) -> List[Dict[str, Any]]:
    # MMR on candidate rows for diversity-preserving rerank.
    if not rows:
        return rows
    row_indices = [int(r.get("row_index", -1)) for r in rows]
    valid = [(i, ridx) for i, ridx in enumerate(row_indices) if 0 <= ridx < len(mcq_df)]
    if len(valid) < 2:
        return rows
    local_rows = [rows[i] for i, _ in valid]
    local_idx = [ridx for _, ridx in valid]
    rel = np.array([float(r.get("hybrid_score", r.get("score", 0.0))) for r in local_rows], dtype=np.float64)
    rel = _minmax(rel)

    selected: List[int] = []
    remaining = list(range(len(local_rows)))
    while remaining:
        if not selected:
            best = max(remaining, key=lambda x: rel[x])
            selected.append(best)
            remaining.remove(best)
            continue
        best_cand = None
        best_val = -1e9
        for cand in remaining:
            cand_vec = tfidf_matrix[local_idx[cand]]
            max_sim = 0.0
            for s in selected:
                sel_vec = tfidf_matrix[local_idx[s]]
                sim = float(cosine_similarity(cand_vec, sel_vec)[0][0])
                if sim > max_sim:
                    max_sim = sim
            mmr = (lambda_mult * rel[cand]) - ((1.0 - lambda_mult) * max_sim)
            if mmr > best_val:
                best_val = mmr
                best_cand = cand
        if best_cand is None:
            break
        selected.append(best_cand)
        remaining.remove(best_cand)

    reordered = [local_rows[i] for i in selected]
    others = [rows[i] for i in range(len(rows)) if i not in {v[0] for v in valid}]
    return reordered + others


def rerank_diversity_layer(
    ranked_candidates: List[Dict[str, Any]],
    mcq_df: pd.DataFrame,
    tfidf_matrix: Any,
) -> List[Dict[str, Any]]:
    # Layer 4: rerank + diversity (MMR + near-duplicate suppression).
    mmr_ranked = _mmr_rerank(ranked_candidates, mcq_df, tfidf_matrix=tfidf_matrix, lambda_mult=0.75)
    deduped: List[Dict[str, Any]] = []
    seen_qtext: Set[str] = set()
    for r in mmr_ranked:
        ridx = int(r.get("row_index", -1))
        qtxt = _norm_text_key(str(mcq_df.iloc[ridx].get("question", ""))) if 0 <= ridx < len(mcq_df) else ""
        if qtxt and qtxt in seen_qtext:
            continue
        if qtxt:
            seen_qtext.add(qtxt)
        deduped.append(r)
    return deduped


def _ensure_tfidf_cache(mcq_df: pd.DataFrame) -> Tuple[TfidfVectorizer, Any, List[str]]:
    ids = [str(v) for v in mcq_df.get("id", pd.Series(range(len(mcq_df)))).tolist()]
    signature = (len(mcq_df), tuple(ids[:20]), tuple(ids[-20:]) if len(ids) > 20 else tuple(ids))
    if (
        _TFIDF_CACHE.get("signature") == signature
        and _TFIDF_CACHE.get("vectorizer") is not None
        and _TFIDF_CACHE.get("matrix") is not None
        and isinstance(_TFIDF_CACHE.get("texts"), list)
    ):
        return _TFIDF_CACHE["vectorizer"], _TFIDF_CACHE["matrix"], _TFIDF_CACHE["texts"]

    texts = [_question_text(mcq_df.iloc[i]) for i in range(len(mcq_df))]
    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(texts)
    _TFIDF_CACHE["signature"] = signature
    _TFIDF_CACHE["vectorizer"] = vectorizer
    _TFIDF_CACHE["matrix"] = matrix
    _TFIDF_CACHE["texts"] = texts
    return vectorizer, matrix, texts


def compute_hybrid_scores(
    query_text: str,
    tfidf_scores: np.ndarray,
    embedding_scores: np.ndarray,
    tfidf_weight: float = TFIDF_WEIGHT,
    embed_weight: float = EMBED_WEIGHT,
) -> np.ndarray:
    _ = query_text  # retained for modular API/debug extensibility
    tfidf_norm = _minmax(np.asarray(tfidf_scores, dtype=np.float64))
    embed_norm = _minmax(np.asarray(embedding_scores, dtype=np.float64))
    return (tfidf_weight * tfidf_norm) + (embed_weight * embed_norm)


def confirmed_weak_topic_indices(
    topics_order: List[Dict[str, Any]], weak_names: List[str]
) -> Tuple[List[int], Dict[int, str]]:
    """Map topic row index -> matched weak topic label from quiz."""
    idxs: List[int] = []
    labels: Dict[int, str] = {}
    seen: Set[int] = set()
    for name in weak_names:
        if not name:
            continue
        display = clean_topic_display_name(name.strip())
        for i, item in enumerate(topics_order):
            if i in seen:
                continue
            if _topic_matches_weak_label(item["topic"], display) or _topic_matches_weak_label(
                item["topic"], name.strip()
            ):
                idxs.append(i)
                labels[i] = display
                seen.add(i)
    return idxs, labels


def fallback_weak_indices(
    topics_order: List[Dict[str, Any]], weak_files: Set[str]
) -> Tuple[List[int], Dict[int, str]]:
    idxs: List[int] = []
    labels: Dict[int, str] = {}
    for i, item in enumerate(topics_order):
        if item["lecture_file"] in weak_files:
            idxs.append(i)
            labels[i] = _display_label_for_topic_row(item)
    return idxs, labels


def prerequisite_topic_indices_from_map(
    weak_indices: List[int],
    weak_labels: Dict[int, str],
    topics_order: List[Dict[str, Any]],
) -> Tuple[List[int], List[Dict[str, str]]]:
    """Resolve prerequisite concepts for weak topics into topic row indices."""
    if not weak_indices:
        return [], []

    out_indices: List[int] = []
    seen: Set[int] = set()
    pairs: List[Dict[str, str]] = []

    for wi in weak_indices:
        weak_label = _norm_concept_key(weak_labels.get(wi) or _display_label_for_topic_row(topics_order[wi]))
        if not weak_label:
            continue
        prereqs: List[str] = []
        for k, vals in DBMS_PREREQUISITES.items():
            nk = _norm_concept_key(k)
            if weak_label == nk or weak_label in nk or nk in weak_label:
                prereqs.extend(vals)
        for prereq in prereqs:
            for j, item in enumerate(topics_order):
                if j == wi:
                    continue
                if not _topic_matches_concept(item["topic"], prereq):
                    continue
                if j not in seen:
                    seen.add(j)
                    out_indices.append(j)
                pairs.append(
                    {
                        "from_weak": clean_topic_display_name(weak_labels.get(wi) or _display_label_for_topic_row(topics_order[wi])),
                        "related_concept": clean_topic_display_name(prereq),
                        "prerequisite_concept": clean_topic_display_name(prereq),
                        "link_type": "Prerequisite concept",
                    }
                )
                break

    return out_indices, pairs


def related_topic_indices_from_graph(
    weak_indices: List[int],
    topics_order: List[Dict[str, Any]],
    sims: np.ndarray,
    priority_files: Set[str],
    max_per_weak: int = 2,
    min_dot_frac: float = 0.08,
) -> Tuple[List[int], List[Dict[str, str]]]:
    """
    Topic–topic similarity = dot product of topic–MCQ similarity rows (dataset-only, no LLM).
    Prefer neighbors in high exam-share lectures as "supporting" concepts.
    """
    if not weak_indices or sims.size == 0:
        return [], []
    n_t, n_q = sims.shape[0], sims.shape[1]
    if n_t < 2 or n_q < 1:
        return [], []
    sims_f = np.asarray(sims, dtype=np.float64)
    tt = sims_f @ sims_f.T
    weak_set = set(weak_indices)
    related: List[int] = []
    seen_j: Set[int] = set()
    pairs: List[Dict[str, str]] = []

    for wi in weak_indices:
        if wi >= n_t:
            continue
        self_norm = float(tt[wi, wi]) + 1e-9
        candidates: List[Tuple[float, int]] = []
        for j in range(n_t):
            if j in weak_set:
                continue
            lf = topics_order[j]["lecture_file"]
            boost = 0.22 if lf in priority_files else 0.0
            val = float(tt[wi, j]) / self_norm + boost
            if float(tt[wi, j]) < min_dot_frac * self_norm and float(tt[wi, j]) < 0.06:
                continue
            candidates.append((val, j))
        candidates.sort(key=lambda x: -x[0])
        picked = 0
        for _, j in candidates:
            if j in seen_j:
                continue
            related.append(j)
            seen_j.add(j)
            wl = _display_label_for_topic_row(topics_order[wi])
            rl = _display_label_for_topic_row(topics_order[j])
            lf = topics_order[j]["lecture_file"]
            link_type = (
                "Supporting topic (high exam share)"
                if lf in priority_files
                else "Related concept (topic similarity)"
            )
            pairs.append({"from_weak": wl, "related_concept": rl, "link_type": link_type})
            picked += 1
            if picked >= max_per_weak:
                break
        # Fallback: if similarity is too sparse, still add one meaningful supporting
        # topic from priority lectures so weak nodes are not isolated.
        if picked == 0:
            fallback_j = None
            fallback_score = -1e9
            for _, j in candidates:
                if j in seen_j:
                    continue
                if topics_order[j]["lecture_file"] not in priority_files:
                    continue
                val = float(tt[wi, j])
                if val > fallback_score:
                    fallback_score = val
                    fallback_j = j
            if fallback_j is None:
                for _, j in candidates:
                    if j not in seen_j:
                        fallback_j = j
                        break
            if fallback_j is not None:
                j = int(fallback_j)
                related.append(j)
                seen_j.add(j)
                wl = _display_label_for_topic_row(topics_order[wi])
                rl = _display_label_for_topic_row(topics_order[j])
                lf = topics_order[j]["lecture_file"]
                link_type = (
                    "Supporting topic (high exam share)"
                    if lf in priority_files
                    else "Related concept (topic similarity)"
                )
                pairs.append({"from_weak": wl, "related_concept": rl, "link_type": link_type})
    return related, pairs


def _build_reason_trace(
    supports_weak: str,
    related_concept: str,
    high_freq: bool,
    prereq_style: bool,
    weak_accuracy_pct: Optional[float] = None,
    exam_frequency_pct: Optional[float] = None,
    prerequisite_path: Optional[List[str]] = None,
    similarity_score: float = 0.0,
    recommendation_rank: Optional[int] = None,
    action: str = "",
) -> Dict[str, Any]:
    lines: List[str] = []
    if supports_weak:
        lines.append(f"Supports weak topic: {supports_weak}")
    if related_concept:
        lines.append(f"Connected concept: {related_concept}")
    if high_freq:
        lines.append("Frequently tested in exams")
    if prereq_style and related_concept:
        lines.append("Useful bridge from a weak area to an important exam theme")
    why = "Recommended for targeted revision."
    weak_signal = (
        f"topic scored {float(weak_accuracy_pct):.0f}% in quiz"
        if weak_accuracy_pct is not None
        else "no direct weak-topic score available"
    )
    exam_signal = (
        f"appears in {float(exam_frequency_pct):.1f}% of past paper questions"
        if exam_frequency_pct is not None
        else "exam-frequency signal unavailable"
    )
    prerequisite_path = prerequisite_path or []
    if not action:
        action = "Review related weak areas and practice suggested MCQs."
    return {
        "supports_weak_topic": supports_weak,
        "related_concept": related_concept,
        "high_frequency_exam": high_freq,
        "why_useful_now": why,
        "lines": lines,
        # Structured explainability fields (additive)
        "weak_signal": weak_signal,
        "exam_frequency": exam_signal,
        "prerequisite_path": prerequisite_path,
        "similarity_score": round(float(similarity_score), 4),
        "recommendation_rank": recommendation_rank,
        "action": action,
    }


def build_map_center_specs(
    topics_order: List[Dict[str, Any]],
    weak_indices: List[int],
    weak_labels: Dict[int, str],
    related_indices: List[int],
    related_pairs: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    from graphrag import graph_builder as gb

    out: List[Dict[str, Any]] = []
    for i in weak_indices:
        if i >= len(topics_order):
            continue
        item = topics_order[i]
        t = item["topic"]
        tid = gb.topic_node_id(t, item["lecture_id"])
        out.append(
            {
                "kind": "weak",
                "row_index": i,
                "lecture_id": item["lecture_id"],
                # Keep topic JSON-light to avoid huge/non-serializable payloads.
                "topic": {
                    "topic_id": t.get("topic_id"),
                    "keywords": list(t.get("keywords", [])[:8]),
                    "rep_sentence": t.get("rep_sentence", ""),
                    "sentences": list(t.get("sentences", [])[:5]),
                },
                "tid": tid,
                "lec_fn": item["lecture_file"],
                "label": weak_labels.get(i) or _display_label_for_topic_row(item),
            }
        )
    pair_by_row: Dict[int, Dict[str, str]] = {}
    for i, p in zip(related_indices, related_pairs):
        pair_by_row[i] = p
    for i in related_indices:
        if i >= len(topics_order):
            continue
        item = topics_order[i]
        t = item["topic"]
        tid = gb.topic_node_id(t, item["lecture_id"])
        rl = _display_label_for_topic_row(item)
        pr = pair_by_row.get(i) or {}
        out.append(
            {
                "kind": "related",
                "row_index": i,
                "lecture_id": item["lecture_id"],
                "topic": {
                    "topic_id": t.get("topic_id"),
                    "keywords": list(t.get("keywords", [])[:8]),
                    "rep_sentence": t.get("rep_sentence", ""),
                    "sentences": list(t.get("sentences", [])[:5]),
                },
                "tid": tid,
                "lec_fn": item["lecture_file"],
                "label": rl,
                "linked_weak_label": pr.get("from_weak", ""),
            }
        )
    return out


def retrieve_recommended_mcqs(
    mcq_df: pd.DataFrame,
    lecture_data: List[Dict[str, Any]],
    sims: np.ndarray,
    quiz_state: Optional[Dict[str, Any]] = None,
    top_priority_n: int = NUM_TOP_PRIORITY_LECTURES,
    top_k: int = 10,
    use_hybrid_scoring: bool = USE_HYBRID_SCORING_DEFAULT,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Score each dataset MCQ; return top_k recommendations with reasons, reason_trace, and scores (0–100).
    """
    if mcq_df.empty:
        return [], {"priority_files": [], "weak_files": [], "strong_files": []}

    quiz_state = quiz_state or load_quiz_state()
    acc_map = lecture_accuracy_map(quiz_state, lecture_data)
    dist_df, priority_files = priority_lecture_files_from_distribution(
        lecture_data, mcq_df, sims, top_n=top_priority_n
    )
    lecture_freq_pct: Dict[str, float] = {}
    if not dist_df.empty:
        pct_col = "Percentage" if "Percentage" in dist_df.columns else "Percentage_of_Total"
        if pct_col in dist_df.columns and "Lecture_File" in dist_df.columns:
            for _, row in dist_df.iterrows():
                lecture_freq_pct[str(row.get("Lecture_File", ""))] = float(row.get(pct_col, 0.0))

    weak_files: Set[str] = set()
    strong_files: Set[str] = set()
    for lec in lecture_data:
        fn = os.path.basename(lec.get("file", ""))
        stem = _lecture_stem(fn)
        acc = acc_map.get(fn)
        if acc is None:
            acc = acc_map.get(stem)
        band = classify_quiz_accuracy_band(acc)
        if band == "weak":
            weak_files.add(fn)
        elif band == "strong":
            strong_files.add(fn)

    topics_order = topics_in_sims_order(lecture_data)
    lecture_id_to_file = {
        lec["id"]: os.path.basename(lec["file"]) for lec in lecture_data
    }

    weak_topic_indices_lecture: List[int] = []
    priority_topic_indices: List[int] = []
    for i, item in enumerate(topics_order):
        lf = item["lecture_file"]
        if lf in weak_files:
            weak_topic_indices_lecture.append(i)
        if lf in priority_files:
            priority_topic_indices.append(i)

    learning_state = get_learning_state()
    learning_state_weak = list(learning_state.get("weak_topics") or [])
    weak_names = list(quiz_state.get("weak_topics_confirmed") or []) if quiz_state else []
    if learning_state_weak:
        weak_names = list(dict.fromkeys(weak_names + learning_state_weak))
    weak_names_cleaned = [clean_topic_display_name(w) for w in weak_names if str(w).strip()]
    confirmed_idx, confirmed_labels = confirmed_weak_topic_indices(topics_order, weak_names)
    if confirmed_idx:
        weak_topic_indices_primary = confirmed_idx
        weak_labels_by_idx = dict(confirmed_labels)
    else:
        weak_topic_indices_primary, weak_labels_by_idx = fallback_weak_indices(
            topics_order, weak_files
        )

    related_topic_indices, related_pairs = related_topic_indices_from_graph(
        weak_topic_indices_primary,
        topics_order,
        sims,
        priority_files,
        max_per_weak=2,
    )
    prereq_topic_indices, prereq_pairs = prerequisite_topic_indices_from_map(
        weak_topic_indices_primary,
        weak_labels_by_idx,
        topics_order,
    )
    # Ensure prerequisite topics are part of map centers, but keep distinct link metadata.
    combined_related_indices = sorted(set(related_topic_indices) | set(prereq_topic_indices))
    combined_related_pairs = list(related_pairs) + list(prereq_pairs)

    weak_union = sorted(set(weak_topic_indices_primary) | set(weak_topic_indices_lecture))
    related_arr = np.array(combined_related_indices, dtype=int) if combined_related_indices else np.array([], dtype=int)
    prereq_arr = np.array(prereq_topic_indices, dtype=int) if prereq_topic_indices else np.array([], dtype=int)
    prereq_by_row: Dict[int, Dict[str, str]] = {}
    for idx, p in zip(prereq_topic_indices, prereq_pairs):
        prereq_by_row[idx] = p

    nq = len(mcq_df)
    rec_rows: List[Dict[str, Any]] = []
    embedding_signal_vec = np.zeros(nq, dtype=np.float64)

    for j in range(nq):
        row = mcq_df.iloc[j]
        qid = str(row.get("id", j))
        lid = row.get("lecture_id")
        lec_file = lecture_id_to_file.get(lid, "")
        reasons: List[str] = []
        score = 0.0

        acc = acc_map.get(lec_file) or acc_map.get(_lecture_stem(lec_file))
        band = classify_quiz_accuracy_band(acc)

        if band == "weak":
            score += 38.0
            reasons.append("Weak area: lower quiz score on this lecture")
        elif band == "neutral" and acc is not None:
            score += 8.0
            reasons.append("Mixed performance — worth reviewing")

        high_freq = lec_file in priority_files
        if high_freq:
            score += 28.0
            reasons.append("High exam frequency (important in your materials)")

        supports_weak = ""
        related_concept = ""
        prereq_concept = ""
        prereq_paths: List[str] = []
        prereq_style = False
        best_sim_signal = 0.0

        if sims.size > 0 and j < sims.shape[1]:
            col = sims[:, j]

            if weak_topic_indices_primary:
                wi_arr = np.array(weak_topic_indices_primary, dtype=int)
                sim_w = float(np.max(col[wi_arr]))
                best_wi = int(wi_arr[int(np.argmax(col[wi_arr]))])
                supports_weak = weak_labels_by_idx.get(best_wi) or _display_label_for_topic_row(
                    topics_order[best_wi]
                )
            elif weak_union:
                wu = np.array(weak_union, dtype=int)
                sim_w = float(np.max(col[wu]))
                best_wi = int(wu[int(np.argmax(col[wu]))])
                supports_weak = weak_labels_by_idx.get(best_wi) or _display_label_for_topic_row(
                    topics_order[best_wi]
                )
            else:
                sim_w = 0.0

            if sim_w >= 0.22:
                score += 22.0 * min(1.0, sim_w / 0.5)
                reasons.append("Same or very close topic as your weak quiz area (GraphRAG match)")
                best_sim_signal = max(best_sim_signal, sim_w)

            if related_arr.size > 0:
                sim_r = float(np.max(col[related_arr]))
                best_ri = int(related_arr[int(np.argmax(col[related_arr]))])
                related_concept = _display_label_for_topic_row(topics_order[best_ri])
                lf_rel = topics_order[best_ri]["lecture_file"]
                prereq_style = lf_rel in priority_files
                if sim_r >= 0.2:
                    score += 14.0 * min(1.0, sim_r / 0.5)
                    reasons.append(
                        "Related or supporting concept linked through topic similarity (GraphRAG)"
                    )
                    best_sim_signal = max(best_sim_signal, sim_r)
            else:
                sim_r = 0.0

            if prereq_arr.size > 0:
                sim_p = float(np.max(col[prereq_arr]))
                best_pi = int(prereq_arr[int(np.argmax(col[prereq_arr]))])
                pinfo = prereq_by_row.get(best_pi, {})
                prereq_concept = pinfo.get("prerequisite_concept") or pinfo.get("related_concept") or _display_label_for_topic_row(topics_order[best_pi])
                weak_for_prereq = pinfo.get("from_weak") or supports_weak or "weak topic"
                if sim_p >= 0.18:
                    score += 16.0 * min(1.0, sim_p / 0.45)
                    reasons.append(f"Prerequisite concept reinforcement (prerequisite of weak topic: {weak_for_prereq})")
                    prereq_paths = [f"{weak_for_prereq} → {prereq_concept}"]
                    best_sim_signal = max(best_sim_signal, sim_p)
            else:
                sim_p = 0.0

            if len(priority_topic_indices) > 0:
                pri_sim = float(np.max(col[np.array(priority_topic_indices)]))
                if pri_sim >= 0.3 and lec_file not in priority_files:
                    score += 12.0 * min(1.0, pri_sim / 0.55)
                    reasons.append("Linked to a high-priority theme in your course")
                    best_sim_signal = max(best_sim_signal, pri_sim)

            if weak_union and not weak_topic_indices_primary:
                related_sim = float(np.max(col[np.array(weak_union)]))
                if related_sim >= 0.25 and sim_w < 0.22:
                    score += 18.0 * min(1.0, related_sim / 0.5)
                    reasons.append("Related topic: similar to material you found difficult")

        if lec_file in priority_files and band != "weak":
            joined = " ".join(reasons)
            if "High exam frequency" not in joined:
                score += 10.0
                reasons.append("From a high-priority lecture for exams")

        score = min(100.0, score)
        if not reasons:
            reasons.append("Practice question from your materials")

        freq_pct = lecture_freq_pct.get(lec_file)
        if freq_pct is None:
            freq_pct = lecture_freq_pct.get(_lecture_stem(lec_file))
        action = "Review core concept and practice recommended MCQs."
        s_low = (supports_weak or "").lower()
        if "normalization" in s_low:
            action = "Review 1NF → 2NF → 3NF progression."
        elif "transaction" in s_low:
            action = "Review ACID first, then concurrency-control scenarios."
        elif prereq_paths:
            action = f"Start with prerequisite: {prereq_paths[0]}."

        trace = _build_reason_trace(
            supports_weak,
            related_concept,
            high_freq,
            prereq_style,
            weak_accuracy_pct=acc,
            exam_frequency_pct=freq_pct,
            prerequisite_path=prereq_paths,
            similarity_score=best_sim_signal,
            recommendation_rank=None,
            action=action,
        )
        student_reasons = list(dict.fromkeys(trace["lines"] + [trace["why_useful_now"]]))
        merged_reasons = list(dict.fromkeys(student_reasons + reasons))
        primary_topic = prereq_concept or related_concept or supports_weak
        weak_topic_boosted = False
        score_before_weak_boost = score
        if primary_topic and weak_names_cleaned:
            for weak_label in weak_names_cleaned:
                is_match = _labels_match_partial(primary_topic, weak_label)
                if is_match:
                    score += 0.3
                    weak_topic_boosted = True
                    break
        score = min(100.0, score)

        rec_rows.append(
            {
                "question_id": qid,
                "score": round(score, 2),
                "reasons": merged_reasons,
                "reason_trace": trace,
                "recommended_topic": primary_topic,
                "row_index": j,
                "_weak_topic_boosted": weak_topic_boosted,
                "_score_before_weak_boost": round(score_before_weak_boost, 4),
                "_difficulty_level": _estimate_difficulty_level(row, score),
            }
        )
        embedding_signal_vec[j] = float(best_sim_signal)
    # Layer 1: Query understanding
    raw_query = " ".join([str(w).strip() for w in weak_names_cleaned if str(w).strip()]) or "database management system"
    query_ctx = query_understanding_layer(
        raw_query=raw_query,
        weak_topics=weak_names_cleaned,
        related_pairs=related_pairs,
        prereq_pairs=prereq_pairs,
        priority_files=priority_files,
    )

    # Layer 2: Candidate retrieval (wide recall set)
    cand_payload = candidate_retrieval_layer(
        expanded_query=query_ctx,
        mcq_df=mcq_df,
        top_k=top_k,
        multiplier=12,
    )
    tfidf_scores = np.asarray(cand_payload["tfidf_scores"], dtype=np.float64)
    candidate_indices_set = {int(i) for i in cand_payload.get("candidate_indices", [])}
    rec_rows = [r for r in rec_rows if int(r.get("row_index", -1)) in candidate_indices_set]

    # Layer 3: Multi-signal ranking
    rec_rows = ranking_layer(
        rec_rows=rec_rows,
        tfidf_scores=tfidf_scores,
        embedding_signal_vec=embedding_signal_vec,
        use_hybrid_scoring=use_hybrid_scoring,
    )
    for rec in rec_rows:
        rec.setdefault("ranking_explanation", {})
        rec["ranking_explanation"]["query_expansion"] = {
            "base_terms": query_ctx.get("base_terms", []),
            "synonym_terms": query_ctx.get("synonym_terms", []),
            "graph_neighbor_terms": query_ctx.get("graph_neighbor_terms", []),
            "lecture_context_terms": query_ctx.get("lecture_context_terms", []),
        }

    # Layer 4: reranking + diversity
    _, tfidf_matrix, _ = _ensure_tfidf_cache(mcq_df)
    ranked = rerank_diversity_layer(
        ranked_candidates=rec_rows,
        mcq_df=mcq_df,
        tfidf_matrix=tfidf_matrix,
    )
    # Guarantee at least one weak-topic recommendation in top 3.
    if weak_names_cleaned and len(ranked) >= 3:
        has_weak_in_top3 = any(
            _labels_match_partial(rec.get("recommended_topic", ""), weak_label)
            for rec in ranked[:3]
            for weak_label in weak_names_cleaned
        )
        if not has_weak_in_top3:
            swap_idx = None
            for idx in range(3, len(ranked)):
                rec_topic = ranked[idx].get("recommended_topic", "")
                if any(_labels_match_partial(rec_topic, weak_label) for weak_label in weak_names_cleaned):
                    swap_idx = idx
                    break
            if swap_idx is not None:
                ranked[2], ranked[swap_idx] = ranked[swap_idx], ranked[2]
                print(
                    f"[graph_retriever] swapped weak-topic recommendation into top3: "
                    f"from_index={swap_idx} to_index=2 topic='{ranked[2].get('recommended_topic', '')}'"
                )

    for i, rec in enumerate(ranked[:5], start=1):
        print(
            f"[graph_retriever] top5 score_debug rank={i} qid={rec.get('question_id')} "
            f"before_boost={rec.get('_score_before_weak_boost', rec.get('score'))} "
            f"after_boost={rec.get('score')} boosted={rec.get('_weak_topic_boosted', False)} "
            f"tfidf={rec.get('tfidf_score')} embed={rec.get('embedding_score')} "
            f"hybrid={rec.get('hybrid_score')} "
            f"topic='{rec.get('recommended_topic', '')}'"
        )

    for rank, rec in enumerate(ranked, start=1):
        trace = rec.get("reason_trace") or {}
        trace["recommendation_rank"] = rank
        rec["reason_trace"] = trace
        rec.pop("_weak_topic_boosted", None)
        rec.pop("_score_before_weak_boost", None)
    # Keep the full ranked pool; weak/related priority is handled during mix selection.
    candidate_ranked = list(ranked)
    history = _load_student_history()
    attempted_ids = {str(x) for x in (history.get("attempted_question_ids") or []) if str(x)}
    previously_recommended = {str(x) for x in (history.get("recommended_question_ids") or []) if str(x)}

    candidate_after_attempted = [
        r for r in candidate_ranked if str(r.get("question_id", "")) not in attempted_ids
    ]
    candidate_after_recommended = [
        r for r in candidate_after_attempted
        if str(r.get("question_id", "")) not in previously_recommended
    ]

    print(f"[graph_retriever] weak_topics={weak_names_cleaned}")
    print(f"[graph_retriever] candidate_count_before_filter={len(candidate_ranked)}")
    print(f"[graph_retriever] candidate_count_after_attempted_filter={len(candidate_after_attempted)}")
    print(f"[graph_retriever] candidate_count_after_recommended_filter={len(candidate_after_recommended)}")

    # Filter policy:
    # 1) Always exclude attempted first if alternatives exist
    # 2) Exclude previously recommended when enough candidates exist
    # 3) Relax "previously recommended" before relaxing attempted
    # 4) Only include attempted when absolutely no alternatives remain
    if len(candidate_after_recommended) >= top_k:
        non_repeating = list(candidate_after_recommended)
    elif candidate_after_attempted:
        non_repeating = list(candidate_after_attempted)
    elif candidate_after_recommended:
        non_repeating = list(candidate_after_recommended)
    else:
        non_repeating = list(candidate_ranked)

    # Keep widened recall stage.
    pool_size = min(len(non_repeating), max(top_k * 12, top_k * 2))
    pool = list(non_repeating[:pool_size])

    weak_pool: List[Dict[str, Any]] = []
    related_pool: List[Dict[str, Any]] = []
    other_pool: List[Dict[str, Any]] = []
    for r in pool:
        trace = r.get("reason_trace") or {}
        supports_weak = str(trace.get("supports_weak_topic") or "").strip()
        related = str(trace.get("related_concept") or "").strip()
        if supports_weak:
            weak_pool.append(r)
        elif related:
            related_pool.append(r)
        else:
            other_pool.append(r)

    rng = random.SystemRandom()
    rng.shuffle(weak_pool)
    rng.shuffle(related_pool)
    rng.shuffle(other_pool)

    weak_target = max(1, int(round(top_k * 0.6)))
    related_target = max(1, top_k - weak_target)
    selected: List[Dict[str, Any]] = []

    # Topic-aware sampling: cover multiple weak and related concepts first.
    weak_by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for r in weak_pool:
        topic_key = str((r.get("reason_trace") or {}).get("supports_weak_topic") or "").strip() or "weak"
        weak_by_topic.setdefault(topic_key, []).append(r)
    for rows in weak_by_topic.values():
        rng.shuffle(rows)

    related_by_topic: Dict[str, List[Dict[str, Any]]] = {}
    for r in related_pool:
        topic_key = str((r.get("reason_trace") or {}).get("related_concept") or "").strip() or "related"
        related_by_topic.setdefault(topic_key, []).append(r)
    for rows in related_by_topic.values():
        rng.shuffle(rows)

    seen_ids = set()
    weak_topic_keys = list(weak_by_topic.keys())
    rng.shuffle(weak_topic_keys)
    for tk in weak_topic_keys:
        if len(selected) >= weak_target:
            break
        row = weak_by_topic[tk][0]
        qid = str(row.get("question_id", ""))
        if qid and qid not in seen_ids:
            selected.append(row)
            seen_ids.add(qid)

    related_topic_keys = list(related_by_topic.keys())
    rng.shuffle(related_topic_keys)
    for tk in related_topic_keys:
        if len([r for r in selected if str((r.get("reason_trace") or {}).get("related_concept") or "").strip()]) >= related_target:
            break
        row = related_by_topic[tk][0]
        qid = str(row.get("question_id", ""))
        if qid and qid not in seen_ids:
            selected.append(row)
            seen_ids.add(qid)

    # Fill weak target.
    for r in weak_pool:
        if len([x for x in selected if str((x.get("reason_trace") or {}).get("supports_weak_topic") or "").strip()]) >= weak_target:
            break
        qid = str(r.get("question_id", ""))
        if qid and qid not in seen_ids:
            selected.append(r)
            seen_ids.add(qid)

    # Fill related target.
    for r in related_pool:
        if len([x for x in selected if str((x.get("reason_trace") or {}).get("related_concept") or "").strip()]) >= related_target:
            break
        qid = str(r.get("question_id", ""))
        if qid and qid not in seen_ids:
            selected.append(r)
            seen_ids.add(qid)

    # Fill any remaining slots from available pools, preserving non-repetition.
    if len(selected) < top_k:
        leftovers = weak_pool[weak_target:] + related_pool[related_target:] + other_pool
        rng.shuffle(leftovers)
        for r in leftovers:
            qid = str(r.get("question_id", ""))
            if not qid or qid in seen_ids:
                continue
            selected.append(r)
            seen_ids.add(qid)
            if len(selected) >= top_k:
                break
    top = selected[:top_k]
    for rec in top:
        rt = rec.get("reason_trace") or {}
        why_lines = rec.get("reasons") or []
        rec["why_selected"] = why_lines[:3]
        rec["weak_topic_link"] = str(rt.get("supports_weak_topic") or "")
        rec["related_concept"] = str(rt.get("related_concept") or "")
        rec["difficulty_level"] = rec.get("_difficulty_level", "Medium")
        rec["reasoning_trace"] = {
            "ranking_reasons": why_lines[:6],
            "graph_reason_trace": rt,
            "ranking_explanation": rec.get("ranking_explanation") or {},
        }
        rec.pop("_difficulty_level", None)
    print(f"[graph_retriever] final_recommendation_count={len(top)}")
    print(
        "[graph_retriever] final_topic_coverage "
        f"weak={len({str((r.get('reason_trace') or {}).get('supports_weak_topic') or '').strip() for r in top if str((r.get('reason_trace') or {}).get('supports_weak_topic') or '').strip()})} "
        f"related={len({str((r.get('reason_trace') or {}).get('related_concept') or '').strip() for r in top if str((r.get('reason_trace') or {}).get('related_concept') or '').strip()})}"
    )

    # Persist recommendation history to reduce repetition in next sessions.
    new_rec_ids = [str(r.get("question_id", "")) for r in top if str(r.get("question_id", ""))]
    merged_recommended = list(dict.fromkeys((history.get("recommended_question_ids") or []) + new_rec_ids))
    history["recommended_question_ids"] = merged_recommended[-500:]
    history["attempted_question_ids"] = list(dict.fromkeys(history.get("attempted_question_ids") or []))[-1000:]
    _save_student_history(history)

    map_center_specs = build_map_center_specs(
        topics_order,
        weak_topic_indices_primary,
        weak_labels_by_idx,
        combined_related_indices,
        combined_related_pairs,
    )

    dedup_related: List[Dict[str, str]] = []
    seen_pairs: Set[Tuple[str, str]] = set()
    for item in related_pairs:
        fw = clean_topic_display_name(str(item.get("from_weak", "")).strip())
        rc = clean_topic_display_name(str(item.get("related_concept", "")).strip())
        if not fw or not rc:
            continue
        key = (fw.lower(), rc.lower())
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        dedup_related.append(
            {"from_weak": fw, "related_concept": rc, "link_type": item.get("link_type", "")}
        )
        if len(dedup_related) >= 5:
            break

    dedup_prereq: List[Dict[str, str]] = []
    seen_pr: Set[Tuple[str, str]] = set()
    for item in prereq_pairs:
        fw = clean_topic_display_name(str(item.get("from_weak", "")).strip())
        pc = clean_topic_display_name(
            str(item.get("prerequisite_concept") or item.get("related_concept") or "").strip()
        )
        if not fw or not pc:
            continue
        key = (fw.lower(), pc.lower())
        if key in seen_pr:
            continue
        seen_pr.add(key)
        dedup_prereq.append(
            {
                "from_weak": fw,
                "related_concept": pc,
                "prerequisite_concept": pc,
                "link_type": item.get("link_type", "Prerequisite concept"),
            }
        )
        if len(dedup_prereq) >= 5:
            break

    meta: Dict[str, Any] = {
        "priority_files": sorted(priority_files),
        "weak_files": sorted(weak_files),
        "strong_files": sorted(strong_files),
        "has_quiz_state": quiz_state is not None,
        "weak_topics_confirmed": [clean_topic_display_name(w) for w in weak_names],
        "related_concept_links": dedup_related,
        "prerequisite_concept_links": dedup_prereq,
        "map_center_specs": map_center_specs,
        "uses_confirmed_weak_topics": bool(confirmed_idx),
        "history_counts": {
            "attempted": len(attempted_ids),
            "previously_recommended": len(previously_recommended),
        },
        "recommendation_mix": {
            "target_total": int(top_k),
            "weak_target": int(weak_target),
            "related_target": int(related_target),
            "selected_total": len(top),
            "candidate_pool_size_before_rerank": int(pool_size),
        },
        "ranking": {
            "use_hybrid_scoring": bool(use_hybrid_scoring),
            "tfidf_weight": TFIDF_WEIGHT,
            "embedding_weight": EMBED_WEIGHT,
            "query_expansion": {
                "base_terms": query_ctx.get("base_terms", []),
                "synonym_terms": query_ctx.get("synonym_terms", []),
                "graph_neighbor_terms": query_ctx.get("graph_neighbor_terms", []),
                "lecture_context_terms": query_ctx.get("lecture_context_terms", []),
            },
        },
        "learning_state_snapshot": {
            "weak_topics": learning_state_weak,
            "strong_topics": list(learning_state.get("strong_topics") or []),
            "mastered_topics": list(learning_state.get("mastered_topics") or []),
            "confidence_score": dict(learning_state.get("confidence_score") or {}),
        },
        "edge_explanations": {
            "weak_to_related": [
                {
                    "from_weak": clean_topic_display_name(str(x.get("from_weak", "")).strip()),
                    "to_related": clean_topic_display_name(str(x.get("related_concept", "")).strip()),
                    "why": str(x.get("link_type", "Related by semantic neighborhood")),
                }
                for x in dedup_related
            ],
            "weak_to_prerequisite": [
                {
                    "from_weak": clean_topic_display_name(str(x.get("from_weak", "")).strip()),
                    "to_prerequisite": clean_topic_display_name(
                        str(x.get("prerequisite_concept") or x.get("related_concept") or "").strip()
                    ),
                    "why": str(x.get("link_type", "Prerequisite concept")),
                }
                for x in dedup_prereq
            ],
        },
    }
    return top, meta


def save_recommendations(
    recommendations: List[Dict[str, Any]],
    meta: Dict[str, Any],
    path: Optional[Path] = None,
) -> None:
    def _to_jsonable(obj: Any) -> Any:
        if isinstance(obj, (str, int, float, bool)) or obj is None:
            return obj
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            clean: Dict[str, Any] = {}
            for k, v in obj.items():
                # Drop heavy non-essential vectors if present in nested topic dicts.
                if k in {"embeddings", "centroid_embedding", "topic_embeddings"}:
                    continue
                clean[str(k)] = _to_jsonable(v)
            return clean
        if isinstance(obj, (list, tuple, set)):
            return [_to_jsonable(v) for v in obj]
        return str(obj)

    p = path or DEFAULT_RECOMMENDATIONS_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "recommendations": _to_jsonable(recommendations),
            "meta": _to_jsonable(meta),
        }
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, p)
    except (OSError, TypeError, ValueError):
        pass
