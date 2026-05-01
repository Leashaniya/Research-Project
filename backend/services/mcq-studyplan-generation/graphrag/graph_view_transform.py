"""
Learning-map transformation: hard caps on topics/MCQs for student-friendly PyVis.
Does not change GraphRAG retrieval or scoring — only filters what is drawn.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from analysis_utils import lecture_mcq_share_dataframe
from graphrag import graph_builder as gb
from topic_labels import clean_topic_keyword_chip

# Strict caps (learning map)
MAX_TOPIC_CLUSTERS = 8
MAX_WEAK_TOPIC_NODES = 5
MAX_MCQ_NODES = 10
MAX_RELATED_TOPIC_NODES = 8
MAX_WEAK_TO_RELATED_EDGES = 8


def _basename(path: str) -> str:
    return os.path.basename(path or "")


def topic_node_id(topic: Dict[str, Any], lecture_id: str) -> str:
    return gb.topic_node_id(topic, lecture_id)


def _topic_kw_line(topic: Dict[str, Any]) -> str:
    kws = topic.get("keywords", [])[:5]
    parts = [clean_topic_keyword_chip(k) for k in kws if k]
    return ", ".join(parts) or "Main ideas"


def topic_learning_label(kind: str, topic: Dict[str, Any]) -> str:
    line = _topic_kw_line(topic)
    if kind == "weak":
        return f"Weak Topic: {line}"
    if kind == "related":
        return f"Related concept: {line}"
    if kind == "priority":
        return f"Important Topic: {line}"
    return f"Topic: {line}"


def topic_student_label(
    topic: Dict[str, Any],
    lec_fn: str,
    weak_files: Set[str],
    strong_files: Set[str],
    priority_files: Set[str],
) -> str:
    """Human-readable labels (legacy helper for imports)."""
    line = _topic_kw_line(topic)
    if lec_fn in weak_files:
        return f"Weak Topic: {line}"
    if lec_fn in strong_files:
        return f"Strong Topic: {line}"
    if lec_fn in priority_files:
        return f"Important Topic: {line}"
    return f"Topic: {line}"


def _topic_keywords_set(topic: Dict[str, Any]) -> Set[str]:
    return {str(k).lower() for k in topic.get("keywords", [])[:12] if k}


def mcq_column_index_for_row(mcq_df: pd.DataFrame, row_index: int) -> int:
    for j, (idx, _) in enumerate(mcq_df.iterrows()):
        if j == row_index or idx == row_index:
            return j
    return row_index if 0 <= row_index < len(mcq_df) else 0


def best_topic_id_for_mcq_column(
    mcq_col: int,
    lecture_id: str,
    topics_order: List[Dict[str, Any]],
    sims: np.ndarray,
    allowed_topic_ids: Set[str],
) -> Optional[str]:
    best_tid: Optional[str] = None
    best_s = -1.0
    for i, item in enumerate(topics_order):
        if item["lecture_id"] != lecture_id:
            continue
        tid = topic_node_id(item["topic"], lecture_id)
        if tid not in allowed_topic_ids:
            continue
        if sims.size == 0 or mcq_col >= sims.shape[1] or i >= sims.shape[0]:
            s = 0.0
        else:
            s = float(sims[i, mcq_col])
        if s > best_s:
            best_s = s
            best_tid = tid
    if best_tid:
        return best_tid
    for item in topics_order:
        if item["lecture_id"] != lecture_id:
            continue
        tid = topic_node_id(item["topic"], lecture_id)
        if tid in allowed_topic_ids:
            return tid
    return None


def build_topics_order(lecture_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for lec in lecture_data:
        lid = lec["id"]
        lfile = _basename(lec.get("file", ""))
        for topic in lec.get("topics") or []:
            out.append(
                {"topic": topic, "lecture_id": lid, "lecture_file": lfile}
            )
    return out


def build_learning_map_bundle(
    lecture_data: List[Dict[str, Any]],
    mcq_df: pd.DataFrame,
    sims: np.ndarray,
    recommendations: List[Dict[str, Any]],
    meta: Dict[str, Any],
    acc_map: Dict[str, float],
) -> Dict[str, Any]:
    """
    Select small topic clusters (weak + related + optional priority) and
    up to MAX_MCQ_NODES recommended MCQs linked to those topics (GraphRAG learning map).
    """
    weak_files: Set[str] = set(meta.get("weak_files", []))
    priority_files: Set[str] = set(meta.get("priority_files", []))

    specs = meta.get("map_center_specs") or []
    if specs:
        centers = []
        seen_labels: Set[Tuple[str, str]] = set()
        weak_count = 0
        related_count = 0
        for s in specs[:20]:
            lec = next(
                (L for L in lecture_data if L["id"] == s.get("lecture_id")),
                None,
            )
            if not lec:
                continue
            kind = s.get("kind", "priority")
            label_norm = str(s.get("label", "")).strip().lower()
            key = (kind, label_norm)
            if label_norm and key in seen_labels:
                continue
            if label_norm:
                seen_labels.add(key)
            if kind == "weak":
                if weak_count >= MAX_WEAK_TOPIC_NODES:
                    continue
                weak_count += 1
            if kind == "related":
                if related_count >= MAX_RELATED_TOPIC_NODES:
                    continue
                related_count += 1
            centers.append(
                {
                    "kind": kind,
                    "lecture": lec,
                    "topic": s["topic"],
                    "tid": s["tid"],
                    "lec_fn": s.get("lec_fn") or _basename(lec.get("file", "")),
                    "student_label": s.get("label", ""),
                    "linked_weak_label": s.get("linked_weak_label", ""),
                }
            )
        topic_ids = {c["tid"] for c in centers}
        center_lids = {c["lecture"]["id"] for c in centers}
        topics_order = build_topics_order(lecture_data)

        practice_recs: List[Dict[str, Any]] = []
        practice_seen: Set[str] = set()
        for r in recommendations:
            if len(practice_recs) >= MAX_MCQ_NODES:
                break
            j = int(r.get("row_index", -1))
            if j < 0 or j >= len(mcq_df):
                continue
            qid = str(r.get("question_id", "")).strip()
            if qid and qid in practice_seen:
                continue
            lid = mcq_df.iloc[j].get("lecture_id")
            col = mcq_column_index_for_row(mcq_df, j)
            link_tid = best_topic_id_for_mcq_column(
                col, lid, topics_order, sims, topic_ids
            )
            if link_tid is not None:
                practice_recs.append(r)
                if qid:
                    practice_seen.add(qid)
                continue
            if lid in center_lids:
                practice_recs.append(r)
                if qid:
                    practice_seen.add(qid)

        # If center-link filtering is too strict, fill from remaining recommendations
        # so graph keeps the expected 8-10 practice MCQs.
        if len(practice_recs) < MAX_MCQ_NODES:
            for r in recommendations:
                if len(practice_recs) >= MAX_MCQ_NODES:
                    break
                qid = str(r.get("question_id", "")).strip()
                if qid and qid in practice_seen:
                    continue
                practice_recs.append(r)
                if qid:
                    practice_seen.add(qid)

        related_edges: List[Tuple[str, str, str]] = []
        weak_tids = [c["tid"] for c in centers if c["kind"] == "weak"]
        seen_e: Set[Tuple[str, str]] = set()
        for c in centers:
            if c["kind"] != "related":
                continue
            lw = (c.get("linked_weak_label") or "").strip()
            matched = False
            for w in centers:
                if w["kind"] != "weak":
                    continue
                if lw and (w.get("student_label") or "") != lw:
                    continue
                key = (w["tid"], c["tid"])
                if key in seen_e:
                    continue
                seen_e.add(key)
                related_edges.append((w["tid"], c["tid"], "Leads to"))
                matched = True
                break
            if not matched and weak_tids:
                key = (weak_tids[0], c["tid"])
                if key not in seen_e:
                    seen_e.add(key)
                    related_edges.append((weak_tids[0], c["tid"], "Leads to"))
        while len(related_edges) > 14:
            related_edges.pop()

        lecture_ids_show = {c["lecture"]["id"] for c in centers}
        for rec in practice_recs:
            j = int(rec.get("row_index", 0))
            if 0 <= j < len(mcq_df):
                lecture_ids_show.add(mcq_df.iloc[j].get("lecture_id"))

        return {
            "centers": centers,
            "topic_ids": topic_ids,
            "lecture_ids_to_show": lecture_ids_show,
            "practice_recs": practice_recs,
            "topics_order": topics_order,
            "related_edges": related_edges,
            "weak_files": weak_files,
            "strong_files": set(meta.get("strong_files", [])),
            "priority_files": priority_files,
        }

    dist = lecture_mcq_share_dataframe(lecture_data, mcq_df, sims)
    priority_ordered: List[str] = []
    if not dist.empty and "Lecture_File" in dist.columns:
        for _, row in dist.iterrows():
            priority_ordered.append(str(row["Lecture_File"]))

    centers: List[Dict[str, Any]] = []
    used_fn: Set[str] = set()

    # Lowest quiz accuracy lectures first → weak topic nodes
    acc_pairs: List[Tuple[float, Any, str]] = []
    for lec in lecture_data:
        fn = _basename(lec.get("file", ""))
        stem = fn.replace(".pdf", "").replace(".PDF", "")
        a = acc_map.get(fn)
        if a is None:
            a = acc_map.get(stem)
        if a is not None:
            acc_pairs.append((float(a), lec, fn))
    acc_pairs.sort(key=lambda x: x[0])

    for _, lec, fn in acc_pairs:
        if len(centers) >= MAX_WEAK_TOPIC_NODES:
            break
        topics = lec.get("topics") or []
        if not topics:
            continue
        t = topics[0]
        tid = topic_node_id(t, lec["id"])
        centers.append(
            {
                "kind": "weak",
                "lecture": lec,
                "topic": t,
                "tid": tid,
                "lec_fn": fn,
            }
        )
        used_fn.add(fn)

    # Priority / important topics (exam share), fill remaining slots (max 3 clusters)
    for fn in priority_ordered:
        if len(centers) >= MAX_TOPIC_CLUSTERS:
            break
        if fn in used_fn:
            continue
        lec = next(
            (L for L in lecture_data if _basename(L.get("file", "")) == fn),
            None,
        )
        if not lec:
            continue
        topics = lec.get("topics") or []
        if not topics:
            continue
        t = topics[0]
        tid = topic_node_id(t, lec["id"])
        centers.append(
            {
                "kind": "priority",
                "lecture": lec,
                "topic": t,
                "tid": tid,
                "lec_fn": fn,
            }
        )
        used_fn.add(fn)

    # No quiz / no weak: show up to 3 priority-only clusters
    if not centers and priority_ordered:
        for fn in priority_ordered:
            if len(centers) >= MAX_TOPIC_CLUSTERS:
                break
            lec = next(
                (L for L in lecture_data if _basename(L.get("file", "")) == fn),
                None,
            )
            if not lec:
                continue
            topics = lec.get("topics") or []
            if not topics:
                continue
            t = topics[0]
            tid = topic_node_id(t, lec["id"])
            centers.append(
                {
                    "kind": "priority",
                    "lecture": lec,
                    "topic": t,
                    "tid": tid,
                    "lec_fn": _basename(lec.get("file", "")),
                }
            )

    # Fallback: first lecture with topics
    if not centers and lecture_data:
        lec = lecture_data[0]
        topics = lec.get("topics") or []
        if topics:
            fn = _basename(lec.get("file", ""))
            t = topics[0]
            tid = topic_node_id(t, lec["id"])
            centers.append(
                {
                    "kind": "priority",
                    "lecture": lec,
                    "topic": t,
                    "tid": tid,
                    "lec_fn": fn,
                }
            )

    center_lids = {c["lecture"]["id"] for c in centers}
    topic_ids = {c["tid"] for c in centers}

    practice_recs: List[Dict[str, Any]] = []
    practice_seen: Set[str] = set()
    for r in recommendations:
        if len(practice_recs) >= MAX_MCQ_NODES:
            break
        j = int(r.get("row_index", -1))
        if j < 0 or j >= len(mcq_df):
            continue
        qid = str(r.get("question_id", "")).strip()
        if qid and qid in practice_seen:
            continue
        lid = mcq_df.iloc[j].get("lecture_id")
        if lid in center_lids:
            practice_recs.append(r)
            if qid:
                practice_seen.add(qid)

    # Same safeguard in fallback mode: keep graph rich even if center_lids match is narrow.
    if len(practice_recs) < MAX_MCQ_NODES:
        for r in recommendations:
            if len(practice_recs) >= MAX_MCQ_NODES:
                break
            qid = str(r.get("question_id", "")).strip()
            if qid and qid in practice_seen:
                continue
            practice_recs.append(r)
            if qid:
                practice_seen.add(qid)

    topics_order = build_topics_order(lecture_data)

    # Optional: one weak → one related priority topic edge (vocabulary)
    related_edges: List[Tuple[str, str, str]] = []
    weak_centers = [c for c in centers if c["kind"] == "weak"]
    pri_centers = [c for c in centers if c["kind"] == "priority"]
    for wc in weak_centers:
        if len(related_edges) >= MAX_WEAK_TO_RELATED_EDGES:
            break
        w_tid = wc["tid"]
        w_kw = _topic_keywords_set(wc["topic"])
        best_pc = None
        best_score = 0
        for pc in pri_centers:
            p_kw = _topic_keywords_set(pc["topic"])
            shared = w_kw & p_kw
            if len(shared) > best_score:
                best_score = len(shared)
                best_pc = pc
        if best_pc and best_score > 0:
            related_edges.append(
                (
                    w_tid,
                    best_pc["tid"],
                    "Leads to",
                )
            )

    lecture_ids_show = {c["lecture"]["id"] for c in centers}
    for rec in practice_recs:
        j = int(rec.get("row_index", 0))
        if 0 <= j < len(mcq_df):
            lecture_ids_show.add(mcq_df.iloc[j].get("lecture_id"))

    return {
        "centers": centers,
        "topic_ids": topic_ids,
        "lecture_ids_to_show": lecture_ids_show,
        "practice_recs": practice_recs,
        "topics_order": topics_order,
        "related_edges": related_edges,
        "weak_files": weak_files,
        "strong_files": set(meta.get("strong_files", [])),
        "priority_files": priority_files,
    }


# Backwards-compatible name for imports expecting bundle keys
def build_student_view_bundle(
    lecture_data: List[Dict[str, Any]],
    mcq_df: pd.DataFrame,
    sims: np.ndarray,
    recommendations: List[Dict[str, Any]],
    meta: Dict[str, Any],
    acc_map: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Deprecated path — use build_learning_map_bundle with acc_map from caller."""
    from graphrag.graph_retriever import lecture_accuracy_map, load_quiz_state

    qs = load_quiz_state()
    am = acc_map if acc_map is not None else lecture_accuracy_map(qs, lecture_data)
    return build_learning_map_bundle(
        lecture_data, mcq_df, sims, recommendations, meta, am
    )
