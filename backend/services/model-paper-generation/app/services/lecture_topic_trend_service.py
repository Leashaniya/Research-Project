"""
Paper B: derive top_topic / topic_frequencies from lecture slide chunks using
MiniLM embeddings + KMeans. Maps each cluster to a canonical pattern label
via classify_pattern() so template/orchestrator logic stays compatible.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sklearn.cluster import KMeans
from sentence_transformers import SentenceTransformer

from app.core.paths import SLIDES_EXTRACTION_DIR

# Reuse stable pattern taxonomy + text cleanup from preprocessing script
from scripts.structure_topics_template import (
    classify_pattern,
    clean_for_vector,
    get_representative_terms,
)

CHUNKS_FILE = SLIDES_EXTRACTION_DIR / "slides_chunks.jsonl"
MIN_WORDS_PER_CHUNK = 20
MAX_CHUNKS_FOR_CLUSTERING = 1400
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _fallback_trend(reason: str) -> Dict[str, Any]:
    return {
        "top_topic": "GENERAL_THEORY",
        "topic_frequencies": {"GENERAL_THEORY": 1},
        "total_questions_counted": 1,
        "recent_papers_used": [],
        "trend_source": "lecture_slides_fallback",
        "lecture_trend_fallback_reason": reason,
    }


def compute_lecture_slide_trend_sync(num_slots: int) -> Dict[str, Any]:
    """
    Synchronous CPU-bound work: load chunks, embed, cluster, map to pattern labels.
    Called via asyncio.to_thread from the orchestrator.
    """
    path = Path(CHUNKS_FILE)
    if not path.exists():
        return _fallback_trend("slides_chunks.jsonl_missing")

    chunks: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                chunks.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    texts_raw: List[str] = []
    stems_per_index: List[str] = []
    for c in chunks:
        t = clean_for_vector(c.get("text") or "")
        if len(t.split()) < MIN_WORDS_PER_CHUNK:
            continue
        texts_raw.append(t[:8000])
        stems_per_index.append(str(c.get("pdf_stem") or "unknown"))

    if len(texts_raw) < 3:
        return _fallback_trend("insufficient_lecture_chunks")

    # Deterministic subsample if corpus is huge
    if len(texts_raw) > MAX_CHUNKS_FOR_CLUSTERING:
        step = max(1, len(texts_raw) // MAX_CHUNKS_FOR_CLUSTERING)
        texts_raw = texts_raw[::step]
        stems_per_index = stems_per_index[::step]

    model = SentenceTransformer(MODEL_NAME)
    X = model.encode(
        texts_raw,
        show_progress_bar=False,
        convert_to_numpy=True,
    )
    X = np.asarray(X, dtype=np.float32)

    n_clusters = min(max(3, int(num_slots or 4)), 12, len(texts_raw))
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init="auto")
    labels = kmeans.fit_predict(X)

    pattern_weights: Counter = Counter()
    cluster_by_pattern: Dict[str, List[int]] = {}

    for c in range(n_clusters):
        idxs = [i for i, lb in enumerate(labels) if lb == c]
        cluster_texts = [texts_raw[i] for i in idxs]
        if not cluster_texts:
            continue
        keywords = get_representative_terms(model, cluster_texts, top_n=12)
        combo = " ".join(keywords) + " " + cluster_texts[0][:600]
        pattern = classify_pattern(combo)
        weight = len(idxs)
        pattern_weights[pattern] += weight
        cluster_by_pattern.setdefault(pattern, []).extend(idxs)

    if not pattern_weights:
        return _fallback_trend("no_pattern_from_clusters")

    top_topic = sorted(
        pattern_weights.items(),
        key=lambda kv: (-kv[1], kv[0]),
    )[0][0]

    stems_used: List[str] = []
    for pat, _ in pattern_weights.most_common(3):
        for i in cluster_by_pattern.get(pat, [])[:50]:
            if 0 <= i < len(stems_per_index):
                stems_used.append(stems_per_index[i])
    stems_used = sorted(set(stems_used))

    return {
        "top_topic": top_topic,
        "topic_frequencies": dict(pattern_weights),
        "total_questions_counted": int(sum(pattern_weights.values())),
        "recent_papers_used": stems_used,
        "trend_source": "lecture_slides_minilm_kmeans",
        "lecture_chunk_count": len(texts_raw),
        "lecture_clusters": int(n_clusters),
    }
