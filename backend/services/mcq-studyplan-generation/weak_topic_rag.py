"""Lightweight weak-topic RAG summary (in-memory, no external vector DB)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args, **kwargs):  # type: ignore
        return False

from learning_state import get_learning_state
from mcq_utils import embedder
from pdf_utils import extract_text_from_pdf
from topic_labels import clean_topic_display_name

OUTPUT_JSON = Path("outputs") / "weak_topic_rag_summary.json"
OUTPUT_MD = Path("outputs") / "weak_topic_rag_summary.md"
QUIZ_STATE_JSON = Path("outputs") / "graphrag_quiz_state.json"

CHUNK_WORDS = 400
CHUNK_OVERLAP_WORDS = 50
TOP_K_CHUNKS = 4
LA_CANDIDATE_MULTIPLIER = 4

# Current weak-topic policy (aligned with evaluation_utils bands: weak < 50%, moderate 50–70%, strong > 70%).
WEAK_ACCURACY_THRESHOLD = 0.5
# Chunk must look related to the weak topic (lexical + embedding gate).
MIN_WEAK_TOPIC_RELEVANCE = 0.10
MIN_EMBEDDING_SIM_WEAK = 0.18
MIN_COMBINED_GATE = 0.17
INSUFFICIENT_MESSAGE = "insufficient_data_from_lectures"

TOPIC_SYNONYMS: Dict[str, List[str]] = {
    "normalization": ["1nf", "2nf", "3nf", "functional dependency"],
    "join": ["inner join", "left join", "outer join", "join condition"],
    "transaction": ["acid", "concurrency control", "serializability"],
    "index": ["indexing", "b-tree", "file organization"],
    "key": ["primary key", "foreign key", "candidate key"],
}

EXAM_PHRASE_PATTERNS: List[str] = [
    "exam question",
    "difference between",
    "best explains",
    "most appropriate",
    "common mistake",
]

_CACHE: Dict[str, Any] = {
    "lecture_signature": "",
    "chunks": [],
    "chunk_embeddings": None,
}

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)


def _split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[\.\?\!])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def _clean_chunk_text(text: str) -> str:
    t = str(text or "")
    # Remove common noisy headers / repeated titles and broken symbols.
    t = re.sub(r"(?i)database management systems.*?lecture\s*\d+\s*[-:–]?", " ", t)
    t = re.sub(r"(?i)\blecture\s*\d+\b", " ", t)
    t = re.sub(r"(?i)\blearning outcomes?\b.*?(?=(?:\.\s)|$)", " ", t)
    t = re.sub(r"(?i)\blecture content\b", " ", t)
    t = re.sub(r"(?i)\blogical database design\b", " ", t)
    t = re.sub(r"(?i)\bconceptual database design\b", " ", t)
    t = re.sub(r"[•\uf0b7\u2022]+", " ", t)
    t = re.sub(r"[□■▪▫◦]+", " ", t)
    t = re.sub(r"\uFFFD", " ", t)
    # Strip "private use" glyphs often emitted by PDF extraction (Wingdings-like).
    t = re.sub(r"[\uE000-\uF8FF]", " ", t)
    # Remove other non-printable control characters except newlines/tabs (which are collapsed anyway).
    t = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", " ", t)
    t = re.sub(r"[_\-]{2,}", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _chunk_text(text: str, chunk_words: int = CHUNK_WORDS, overlap_words: int = CHUNK_OVERLAP_WORDS) -> List[str]:
    words = re.findall(r"\S+", text or "")
    if not words:
        return []
    chunks = []
    step = max(1, chunk_words - overlap_words)
    for i in range(0, len(words), step):
        seg = words[i:i + chunk_words]
        if len(seg) < 80:
            continue
        chunks.append(" ".join(seg))
        if i + chunk_words >= len(words):
            break
    return chunks


def _lecture_signature(lecture_data: List[Dict[str, Any]]) -> str:
    parts = []
    for lec in lecture_data:
        f = str(lec.get("file", ""))
        if not f:
            continue
        try:
            mtime = os.path.getmtime(f)
        except OSError:
            mtime = 0
        parts.append(f"{f}:{mtime}")
    return "|".join(sorted(parts))


def _ensure_chunk_index(lecture_data: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    sig = _lecture_signature(lecture_data)
    if _CACHE["lecture_signature"] == sig and _CACHE["chunks"] and _CACHE["chunk_embeddings"] is not None:
        return _CACHE["chunks"], _CACHE["chunk_embeddings"]

    chunk_rows: List[Dict[str, Any]] = []
    for lec in lecture_data:
        lecture_file = str(lec.get("file", ""))
        lecture_id = os.path.basename(lecture_file)
        topics = lec.get("topics") or []
        topic_labels = []
        for t in topics[:6]:
            kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
            if kws:
                topic_labels.append(kws[0])
        lecture_text = extract_text_from_pdf(lecture_file)
        chunks_for_lecture = _chunk_text(lecture_text)
        for idx, ch in enumerate(chunks_for_lecture):
            chunk_rows.append(
                {
                    "lecture_id": lecture_id,
                    "lecture_name": (lec.get("title") or lecture_id),
                    "page_number": lec.get("page_number"),
                    "chunk_id": f"{lecture_id}::chunk_{idx}",
                    "topics": topic_labels,
                    "text": ch,
                }
            )

    if not chunk_rows:
        return [], np.zeros((0, 384), dtype=np.float32)

    chunk_embeddings = embedder.encode(
        [r["text"] for r in chunk_rows],
        show_progress_bar=False,
        convert_to_numpy=True,
    )

    _CACHE["lecture_signature"] = sig
    _CACHE["chunks"] = chunk_rows
    _CACHE["chunk_embeddings"] = chunk_embeddings
    return chunk_rows, chunk_embeddings


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.array([])
    q = query_vec / (np.linalg.norm(query_vec) + 1e-9)
    m = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
    return m @ q


def _extract_key_points(topic: str, top_chunks: List[Dict[str, Any]]) -> List[str]:
    points = []
    topic_tokens = {t for t in re.findall(r"[a-zA-Z]+", topic.lower()) if len(t) >= 3}
    for row in top_chunks:
        for sent in _split_sentences(_clean_chunk_text(row["text"])):
            sent_l = sent.lower()
            if any(t in sent_l for t in topic_tokens) and len(points) < 6:
                cleaned = sent.strip()
                if cleaned not in points:
                    points.append(cleaned)
    if not points:
        for row in top_chunks:
            points.extend(_split_sentences(_clean_chunk_text(row["text"]))[:2])
            if len(points) >= 6:
                break
    short = []
    for p in points:
        s = re.sub(r"\s+", " ", p).strip()
        if len(s) > 120:
            s = s[:117] + "..."
        if s and s not in short:
            short.append(s)
        if len(short) >= 3:
            break
    return short


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a) + 1e-9)
    nb = float(np.linalg.norm(b) + 1e-9)
    return float(np.dot(a, b) / (na * nb))


def _mmr_select(
    query_vec: np.ndarray,
    sent_vecs: np.ndarray,
    sents: List[str],
    k: int = 3,
    lam: float = 0.75,
) -> List[str]:
    """Maximal Marginal Relevance selection for diversity + relevance."""
    if not sents or sent_vecs.size == 0:
        return []
    sims_to_query = np.array([_cosine(query_vec, sent_vecs[i]) for i in range(len(sents))], dtype=np.float64)
    selected: List[int] = []
    candidates = set(range(len(sents)))
    while candidates and len(selected) < k:
        best_i = None
        best_score = -1e9
        for i in candidates:
            rel = float(sims_to_query[i])
            div = 0.0
            if selected:
                div = max(float(_cosine(sent_vecs[i], sent_vecs[j])) for j in selected)
            score = lam * rel - (1.0 - lam) * div
            if score > best_score:
                best_score = score
                best_i = i
        if best_i is None:
            break
        selected.append(best_i)
        candidates.remove(best_i)
    return [sents[i] for i in selected]


def _shorten_sentence(s: str, max_len: int = 170) -> str:
    s2 = re.sub(r"\s+", " ", str(s or "")).strip()
    # Remove ultra-long comma chains / slide-like lists.
    s2 = re.sub(r"(?:\s*[•\-\u2022]\s*)+", " ", s2)
    if len(s2) <= max_len:
        return s2
    cut = s2[: max_len - 3]
    cut = re.sub(r"\s+\S*$", "", cut).strip()
    return (cut + "...") if cut else (s2[: max_len - 3] + "...")


def _norm_text_key(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _norm_topic_key(topic: str) -> str:
    return clean_topic_display_name(str(topic or "").strip()).lower()


def _find_twa_row(topic: str, topic_wise_accuracy: Dict[str, Any]) -> Dict[str, Any] | None:
    """Match topic display name to topic_wise_accuracy keys (case/format tolerant)."""
    if not topic_wise_accuracy:
        return None
    want = _norm_topic_key(topic)
    for k, row in topic_wise_accuracy.items():
        if _norm_topic_key(str(k)) == want:
            return row if isinstance(row, dict) else {}
    return None


def _band_base(band: str) -> str:
    b = str(band or "").lower().strip()
    if b.endswith("_low_evidence"):
        b = b[: -len("_low_evidence")].strip()
    return b


def _accuracy_fraction(row: Dict[str, Any]) -> float:
    acc = float(row.get("accuracy", 0.0) or 0.0)
    return acc / 100.0 if acc > 1.0 else acc


def _is_current_strict_weak(row: Dict[str, Any]) -> bool:
    """True only for weak performance: exclude strong and moderate."""
    if not row:
        return False
    acc_frac = _accuracy_fraction(row)
    band_raw = str(row.get("band") or row.get("status") or "")
    band = _band_base(band_raw)
    if band in ("strong", "moderate"):
        return False
    if acc_frac >= WEAK_ACCURACY_THRESHOLD:
        return False
    if band == "weak":
        return True
    if acc_frac < WEAK_ACCURACY_THRESHOLD:
        return True
    return False


def _filter_strict_weak_topics(
    learning_weak_topics: List[str],
    topic_wise_accuracy: Dict[str, Any],
) -> List[str]:
    """
    Only topics with a **current** topic_wise_accuracy row that is strictly weak
    (not strong/moderate; accuracy below WEAK_ACCURACY_THRESHOLD).

    Include if label matches EITHER branch:
    - appears in learning_state weak_topics, OR
    - appears only in topic_wise_accuracy as weak (quiz-native OR branch).

    Strong/moderate topics are never included.
    """
    if not topic_wise_accuracy:
        return []

    ls_norm = {_norm_topic_key(x) for x in learning_weak_topics if str(x).strip()}
    priority: List[str] = []
    extra: List[str] = []
    seen: set[str] = set()

    for k, row in topic_wise_accuracy.items():
        if not isinstance(row, dict):
            continue
        if not _is_current_strict_weak(row):
            continue
        disp = clean_topic_display_name(str(k))
        nk = _norm_topic_key(disp)
        if nk in seen:
            continue
        seen.add(nk)
        if nk in ls_norm:
            priority.append(disp)
        else:
            extra.append(disp)

    ordered = priority + extra
    return list(dict.fromkeys(ordered))


def _chunk_weak_topic_relevance(
    chunk: Dict[str, Any], topic: str, expansion_terms: List[str]
) -> float:
    """Lexical relevance of chunk to the weak topic (0..1)."""
    text = _norm_text_key(_clean_chunk_text(chunk.get("text", "")))
    if not text:
        return 0.0
    hits = 0
    checked = 0
    for term in expansion_terms:
        t = term.strip().lower()
        if len(t) < 3:
            continue
        checked += 1
        if t in text:
            hits += 1
    lex = (hits / checked) if checked else 0.0
    tw = {x for x in re.findall(r"[a-zA-Z]+", topic.lower()) if len(x) >= 3}
    overlap = sum(1 for x in tw if x in text) if tw else 0
    tok_score = min(1.0, overlap / max(1, len(tw)))
    return float(min(1.0, 0.55 * lex + 0.45 * tok_score))


def _merge_overlapping_snippets(snippets: List[str], jaccard_min: float = 0.65) -> List[str]:
    """Drop near-duplicate chunk snippets (Jaccard on word sets)."""
    if len(snippets) <= 1:
        return snippets

    def _words(s: str) -> set:
        return {w for w in re.findall(r"[a-zA-Z0-9]+", s.lower()) if len(w) > 2}

    kept: List[str] = []
    for s in snippets:
        ws = _words(s)
        if not ws:
            continue
        dup = False
        for prev in kept:
            pw = _words(prev)
            if not pw:
                continue
            inter = len(ws & pw)
            union = len(ws | pw) or 1
            if inter / union >= jaccard_min:
                dup = True
                break
        if not dup:
            kept.append(s)
    return kept


def _topic_common_mistakes(topic: str) -> List[str]:
    t = (topic or "").lower()
    if "join" in t:
        return ["Mixing up INNER vs LEFT joins in questions.", "Forgetting join condition and getting a Cartesian product."]
    if "aggregation" in t or "group by" in t:
        return ["Using columns in SELECT that are not in GROUP BY or an aggregate.", "Confusing WHERE vs HAVING conditions."]
    if "normal" in t:
        return ["Missing partial/transitive dependencies when normalizing.", "Decomposing tables but losing a key constraint."]
    if "transaction" in t or "acid" in t:
        return ["Confusing isolation with atomicity/durability.", "Not identifying the anomaly type (dirty read, lost update, etc.)."]
    if "jdbc" in t:
        return ["Forgetting to load/register the driver or connection string details.", "Not closing ResultSet/Statement/Connection properly."]
    if "key" in t or "constraint" in t:
        return ["Confusing candidate key vs primary key.", "Not checking referential integrity when using foreign keys."]
    return ["Memorizing terms without knowing when to apply them.", "Skipping MCQ practice after revision."]


def _derive_prerequisite_terms(topic: str, lecture_data: List[Dict[str, Any]]) -> List[str]:
    topic_tokens = {t for t in re.findall(r"[a-zA-Z]+", topic.lower()) if len(t) >= 4}
    hits: List[str] = []
    for lec in lecture_data:
        for t in (lec.get("topics") or []):
            kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
            if not kws:
                continue
            blob = " ".join(k.lower() for k in kws)
            if any(tok in blob for tok in topic_tokens):
                for kw in kws[:3]:
                    norm = kw.lower()
                    if norm not in hits:
                        hits.append(norm)
    return hits[:5]


def _expanded_query_terms(topic: str, lecture_data: List[Dict[str, Any]]) -> List[str]:
    terms = [topic.strip()]
    low = topic.lower()
    for key, vals in TOPIC_SYNONYMS.items():
        if key in low or low in key:
            terms.extend(vals)
    terms.extend(_derive_prerequisite_terms(topic, lecture_data))
    return list(dict.fromkeys([t for t in terms if t]))


def _exam_relevance_weight(chunk: Dict[str, Any], expanded_terms: List[str]) -> float:
    text = str(chunk.get("text", "")).lower()
    if not text:
        return 0.0
    bonus = 0.0
    for p in EXAM_PHRASE_PATTERNS:
        if p in text:
            bonus += 0.22
    for t in expanded_terms:
        if len(t) >= 5 and t.lower() in text:
            bonus += 0.06
    return min(1.0, bonus)


def _weak_topic_importance(topic: str, learning_state: Dict[str, Any]) -> float:
    weak = {str(x).strip().lower() for x in (learning_state.get("weak_topics") or [])}
    if topic.lower() in weak:
        return 1.0
    return 0.55 if weak else 0.4


def _student_history_gap(topic: str, learning_state: Dict[str, Any]) -> float:
    mastered = {str(x).strip().lower() for x in (learning_state.get("mastered_topics") or [])}
    history = list(learning_state.get("quiz_history") or [])
    topic_l = topic.lower()
    if topic_l in mastered:
        return 0.1
    if not history:
        return 0.65
    recent = history[-5:]
    weak_hits = 0
    for item in recent:
        for w in (item.get("weak_topics") or []):
            if str(w).strip().lower() == topic_l:
                weak_hits += 1
    return min(1.0, 0.45 + 0.15 * weak_hits)


def _deduplicate_ranked_indices(indices: np.ndarray, chunks: List[Dict[str, Any]]) -> List[int]:
    kept: List[int] = []
    seen_keys = set()
    for i in indices:
        txt = _clean_chunk_text(chunks[int(i)].get("text", ""))
        key = _norm_text_key(txt[:240])
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)
        kept.append(int(i))
    return kept


def _high_information_rank(text: str, topic: str) -> float:
    sents = _split_sentences(text)
    token_count = len(re.findall(r"[a-zA-Z]+", text))
    topic_hits = sum(1 for tok in re.findall(r"[a-zA-Z]+", topic.lower()) if len(tok) >= 4 and tok in text.lower())
    return min(1.0, (0.35 * min(1.0, len(sents) / 8.0)) + (0.35 * min(1.0, token_count / 180.0)) + (0.3 * min(1.0, topic_hits / 4.0)))


def _deterministic_learning_notes(topic: str, snippets: List[str], mistakes: List[str]) -> Dict[str, Any]:
    if not snippets:
        return {}
    definition = _shorten_sentence(snippets[0], 190)
    key_points = [_shorten_sentence(s, 120) for s in snippets[:4]]
    exam_focus = [
        _shorten_sentence(f"Exams often test conceptual differences in {topic}.", 120),
        _shorten_sentence("Focus on scenario-based interpretation, not memorization.", 120),
    ]
    mcq_patterns = [
        _shorten_sentence(f"Definition-vs-application MCQs for {topic}.", 110),
        _shorten_sentence("Compare two close options and eliminate by constraint/condition.", 120),
    ]
    checklist = [
        f"State one-line definition of {topic}",
        "List 2-3 key rules/conditions",
        "Solve at least 3 topic-focused MCQs",
    ]
    return {
        "concept_definition": definition,
        "definition": definition,
        "why_it_is_important_in_exams": exam_focus,
        "exam_focus": exam_focus,
        "key_points_to_remember": key_points,
        "key_points": key_points,
        "common_mistakes": mistakes[:3],
        "mcq_patterns": mcq_patterns,
        "quick_revision_checklist": checklist,
    }


def _build_fallback_guidance(topic: str, top_chunks: List[Dict[str, Any]], key_points: List[str]) -> Dict[str, Any]:
    # Build a cleaner candidate sentence pool.
    sentence_pool: List[str] = []
    for row in top_chunks:
        raw = _clean_chunk_text(row.get("text", ""))
        for sent in _split_sentences(raw):
            s = sent.strip()
            if len(s) < 35:
                continue
            # Drop very slide-like keyword chains (too many separators).
            if s.count("□") >= 2 or s.count("▢") >= 2:
                continue
            if s not in sentence_pool:
                sentence_pool.append(s)
            if len(sentence_pool) >= 18:
                break
        if len(sentence_pool) >= 18:
            break

    # Pick diverse, most relevant sentences using embeddings.
    chosen_sents: List[str] = []
    if sentence_pool:
        try:
            q_vec = embedder.encode([topic], show_progress_bar=False, convert_to_numpy=True)[0]
            s_vecs = embedder.encode(sentence_pool, show_progress_bar=False, convert_to_numpy=True)
            chosen_sents = _mmr_select(q_vec, s_vecs, sentence_pool, k=3, lam=0.78)
        except Exception:
            chosen_sents = sentence_pool[:3]

    # Convert extractive sentences into a short student summary (template + minimal quoting).
    if chosen_sents:
        main = _shorten_sentence(chosen_sents[0], 170)
        support = _shorten_sentence(chosen_sents[1], 150) if len(chosen_sents) > 1 else ""
        simple_explanation = f"{topic}: {main}"
        if support:
            simple_explanation += f" {support}"
    else:
        simple_explanation = (
            f"{topic} is an important DBMS concept. "
            "Revise the definition and typical exam patterns, then practice a few MCQs."
        )

    # Key points: prefer short fragments from the chosen sentences, then fall back.
    kp: List[str] = []
    for s in chosen_sents:
        ss = _shorten_sentence(s, 95)
        if ss and ss not in kp:
            kp.append(ss)
        if len(kp) >= 4:
            break
    for p in key_points:
        if len(kp) >= 4:
            break
        pp = _shorten_sentence(p, 90)
        if pp and pp not in kp:
            kp.append(pp)
    if not kp:
        kp = [
            f"Definition of {topic} (in one sentence)",
            "When/why it is used",
            "A common exam question pattern",
            "One quick example you can apply",
        ]

    common_mistakes = _topic_common_mistakes(topic)
    return {
        "topic": topic,
        "simple_explanation": simple_explanation[:500],
        "key_points": kp[:4],
        "common_mistakes": common_mistakes[:2],
        "next_action": "Revise this topic, then practice the recommended MCQs.",
    }


def _extract_first_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    # Direct parse
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        pass
    # Fenced or mixed output parse
    m = re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return {}
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _normalize_guidance_payload(topic: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    revision_notes = payload.get("revision_notes") or {}
    definition = str(
        revision_notes.get("concept_definition")
        or revision_notes.get("definition")
        or payload.get("simple_explanation")
        or ""
    ).strip()
    key_points = [str(x).strip() for x in (revision_notes.get("key_points") or revision_notes.get("key_points_to_remember") or []) if str(x).strip()]
    exam_focus = [str(x).strip() for x in (revision_notes.get("exam_focus") or revision_notes.get("why_it_is_important_in_exams") or []) if str(x).strip()]
    common_mistakes = [str(x).strip() for x in (revision_notes.get("common_mistakes") or payload.get("common_mistakes") or []) if str(x).strip()]
    mcq_patterns = [str(x).strip() for x in (revision_notes.get("mcq_patterns") or []) if str(x).strip()]
    checklist = [str(x).strip() for x in (revision_notes.get("quick_revision_checklist") or []) if str(x).strip()]
    if not definition:
        return {}
    notes = {
        "concept_definition": definition[:500],
        "definition": definition[:500],
        "why_it_is_important_in_exams": exam_focus[:4],
        "exam_focus": exam_focus[:4],
        "key_points_to_remember": key_points[:6],
        "key_points": key_points[:6],
        "common_mistakes": common_mistakes[:3],
        "mcq_patterns": mcq_patterns[:4],
        "quick_revision_checklist": checklist[:5],
    }
    next_action = checklist[0] if checklist else "Revise this topic, then practice the recommended MCQs."
    return {
        "topic": topic,
        "simple_explanation": definition[:500],
        "revision_notes": notes,
        "key_points": key_points[:6],
        "common_mistakes": common_mistakes[:3],
        "next_action": next_action[:220],
    }


def _llm_guidance_if_available(
    topic: str,
    top_chunks: List[Dict[str, Any]],
    topic_performance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    context_lines = []
    for c in top_chunks[:TOP_K_CHUNKS]:
        txt = _clean_chunk_text(c.get("text", ""))
        if txt:
            context_lines.append(
                f"[chunk_id={c.get('chunk_id','')} lecture_name={c.get('lecture_name', c.get('lecture_id',''))} page={c.get('page_number','N/A')}] {txt[:900]}"
            )
    if not context_lines:
        return {}
    perf = topic_performance or {}
    quiz_context_line = (
        f"Student weak topic: {topic}; "
        f"quiz_accuracy={perf.get('accuracy', 'N/A')}; "
        f"attempted={perf.get('total', 'N/A')}; "
        f"band={perf.get('band', 'N/A')}"
    )
    prompt = (
        "You are an expert educational tutor helping university students revise for exams.\n\n"
        "You will be given lecture content retrieved from a course database based on a student's weak topic.\n\n"
        "IMPORTANT RULES:\n"
        "- Answer ONLY based on the provided lecture chunks from the student's slides. Do not add any external information.\n"
        "- Use ONLY the provided lecture content.\n"
        "- Do NOT add external knowledge.\n"
        "- Do NOT assume missing information.\n"
        "- If something is not present in the context, ignore it.\n"
        "- Keep explanations simple, clear, and exam-focused.\n"
        "- Your goal is to help students understand and remember for exams.\n\n"
        f"Weak topic: {topic}\n"
        f"{quiz_context_line}\n\n"
        "TASK:\n"
        "Convert the given lecture context into a structured revision note for the weak topic.\n\n"
        "OUTPUT JSON FORMAT:\n"
        "{\n"
        '  "simple_explanation": "...",\n'
        '  "revision_notes": {\n'
        '    "concept_definition": "...",\n'
        '    "why_it_is_important_in_exams": ["..."],\n'
        '    "key_points": ["..."],\n'
        '    "common_mistakes": ["..."],\n'
        '    "mcq_patterns": ["..."],\n'
        '    "quick_revision_checklist": ["..."]\n'
        "  }\n"
        "}\n\n"
        "LECTURE CONTEXT:\n"
        + "\n\n".join(context_lines)
        + "\n\nADDITIONAL INSTRUCTION:\n"
        "- Keep output concise and student-friendly\n"
        "- Do not copy long paragraphs from context\n"
        "- Rephrase and simplify content\n"
        "- Ensure all points are grounded in lecture material only\n"
        "- If insufficient context, return simple_explanation as 'Insufficient lecture context available' and empty lists.\n"
        "- Refer to chunk ids in wording when useful (e.g., 'as seen in chunk ...').\n"
    )

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_key:
        print("[weak_topic_rag] OpenAI key missing; using deterministic fallback")
        return {}
    try:
        from openai import OpenAI

        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict lecture-grounded revision tutor. "
                        "Use only the supplied lecture chunks. "
                        "Never use external knowledge."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=420,
        )
        content = ""
        if getattr(resp, "choices", None):
            msg = resp.choices[0].message
            content = (msg.content or "").strip()
        parsed = _extract_first_json_object(content)
        norm = _normalize_guidance_payload(topic, parsed)
        if norm:
            print(f"[weak_topic_rag] OpenAI grounded summary used for topic='{topic}'")
            return norm
    except Exception as e:
        print(f"[weak_topic_rag] OpenAI summary failed for topic='{topic}': {e}")
    return {}


def _grounded_text(text: str, snippets: List[str]) -> bool:
    t = _norm_text_key(text)
    if not t:
        return False
    tokens = {x for x in re.findall(r"[a-zA-Z]+", t) if len(x) >= 4}
    if not tokens:
        return False
    for sn in snippets:
        st = _norm_text_key(sn)
        overlap = sum(1 for tok in tokens if tok in st)
        if overlap >= 2:
            return True
    return False


def _ground_llm_notes(llm_row: Dict[str, Any], snippets: List[str]) -> Dict[str, Any]:
    if not llm_row:
        return {}
    notes = llm_row.get("revision_notes") or {}
    concept_def = str(notes.get("concept_definition") or "").strip()
    if concept_def and not _grounded_text(concept_def, snippets):
        concept_def = ""
    def _flt(items: List[str]) -> List[str]:
        out = []
        for x in items:
            sx = str(x).strip()
            if sx and _grounded_text(sx, snippets):
                out.append(sx)
        return out
    grounded_notes = {
        "concept_definition": concept_def,
        "definition": concept_def,
        "why_it_is_important_in_exams": _flt(notes.get("why_it_is_important_in_exams") or notes.get("exam_focus") or []),
        "exam_focus": _flt(notes.get("why_it_is_important_in_exams") or notes.get("exam_focus") or []),
        "key_points_to_remember": _flt(notes.get("key_points_to_remember") or notes.get("key_points") or []),
        "key_points": _flt(notes.get("key_points_to_remember") or notes.get("key_points") or []),
        "common_mistakes": _flt(notes.get("common_mistakes") or []),
        "mcq_patterns": _flt(notes.get("mcq_patterns") or []),
        "quick_revision_checklist": _flt(notes.get("quick_revision_checklist") or []),
    }
    if not grounded_notes["concept_definition"]:
        return {}
    return {
        "topic": llm_row.get("topic", ""),
        "simple_explanation": grounded_notes["concept_definition"],
        "revision_notes": grounded_notes,
        "key_points": grounded_notes["key_points"][:6],
        "common_mistakes": grounded_notes["common_mistakes"][:3],
        "next_action": (grounded_notes["quick_revision_checklist"][0] if grounded_notes["quick_revision_checklist"] else "Revise this topic, then practice the recommended MCQs."),
    }


def _lecture_grounded_notes(topic: str, snippets: List[str]) -> Dict[str, Any] | None:
    """Revision fields derived only from lecture snippets (plus mistakes only if grounded)."""
    if not snippets:
        return None
    definition = _shorten_sentence(snippets[0], 200)
    kps = [_shorten_sentence(s, 120) for s in snippets[1:5] if s]
    kps = [k for k in kps if k and k != definition]
    mistakes: List[str] = []
    for m in _topic_common_mistakes(topic):
        if m and _grounded_text(m, snippets):
            mistakes.append(m)
        if len(mistakes) >= 2:
            break
    return {
        "concept_definition": definition,
        "key_points": kps[:4],
        "common_mistakes": mistakes,
        "quick_revision_checklist": [
            f"Reread the retrieved lecture extracts for {topic}, then verify you can explain them in your own words.",
        ],
    }


def _strict_summary_row(
    topic: str,
    simple_explanation: str,
    key_points: List[str],
    common_mistakes: List[str],
    next_action: str,
) -> Dict[str, Any]:
    return {
        "topic": clean_topic_display_name(topic),
        "simple_explanation": simple_explanation,
        "key_points": list(key_points or [])[:8],
        "common_mistakes": list(common_mistakes or [])[:6],
        "next_action": str(next_action or "")[:500],
    }


def _save_outputs(rows: List[Dict[str, Any]]) -> None:
    try:
        OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump({"weak_topic_summary": rows}, f, indent=2)
        md_lines = ["# Weak Topic RAG Summary (current weak topics only, lecture-grounded)", ""]
        for r in rows:
            md_lines.append(f"## {r.get('topic', '')}")
            notes = r.get("revision_notes") or {}
            expl = str(r.get("simple_explanation") or notes.get("concept_definition") or "")
            kps = r.get("key_points") or notes.get("key_points") or []
            cms = r.get("common_mistakes") or notes.get("common_mistakes") or []
            md_lines.append("### Summary (lecture-based)")
            md_lines.append(expl)
            md_lines.append("")
            md_lines.append("### Key points")
            for kp in kps:
                md_lines.append(f"- {kp}")
            md_lines.append("")
            md_lines.append("### Common mistakes (only if grounded in lecture text)")
            for m in cms:
                md_lines.append(f"- {m}")
            md_lines.append("")
            md_lines.append("### Next action")
            md_lines.append(str(r.get("next_action") or ""))
            md_lines.append("")
            md_lines.append("### Retrieval trace (internal)")
            for tr in (r.get("retrieval_trace") or r.get("source_trace") or []):
                md_lines.append(
                    f"- {tr.get('lecture_id','')} | {tr.get('chunk_id','')} | score={tr.get('score', tr.get('similarity_score', 0))} | {tr.get('used_text_snippet','')}"
                )
            md_lines.append("")
        with open(OUTPUT_MD, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines).strip() + "\n")
    except OSError:
        pass


def generate_weak_topic_rag_summary(lecture_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Lecture-grounded revision summaries only for **current** weak topics:
    learning_state weak_topics intersected with topic_wise_accuracy rows that are
    strictly weak (not strong/moderate; accuracy < WEAK_ACCURACY_THRESHOLD).
    """
    ls = get_learning_state()
    quiz_state_local: Dict[str, Any] = {}
    if QUIZ_STATE_JSON.exists():
        try:
            with open(QUIZ_STATE_JSON, "r", encoding="utf-8") as f:
                quiz_state_local = json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            quiz_state_local = {}

    twa = quiz_state_local.get("topic_wise_accuracy") or {}
    learning_weak = [str(t).strip() for t in (ls.get("weak_topics") or []) if str(t).strip()]
    weak_topics = _filter_strict_weak_topics(learning_weak, twa)

    if not weak_topics:
        print("[weak_topic_rag] No topics after strict weak filter (requires learning_state + quiz topic_wise_accuracy weak).")
        return {"weak_topic_summary": []}

    chunks, chunk_embs = _ensure_chunk_index(lecture_data)
    if not chunks or chunk_embs is None or len(chunks) == 0:
        return {"weak_topic_summary": []}

    out_rows: List[Dict[str, Any]] = []
    save_rows: List[Dict[str, Any]] = []
    seen_topics: set[str] = set()

    for topic in weak_topics:
        tnorm = topic.lower()
        if tnorm in seen_topics:
            continue
        seen_topics.add(tnorm)

        topic_perf = _find_twa_row(topic, twa) or {}

        expansion_terms = _expanded_query_terms(topic, lecture_data)
        q_text = " ".join(expansion_terms)
        q_vec = embedder.encode([q_text], show_progress_bar=False, convert_to_numpy=True)[0]
        sim_scores = _cosine_scores(q_vec, chunk_embs)
        if sim_scores.size == 0:
            row = _strict_summary_row(topic, INSUFFICIENT_MESSAGE, [], [], "Retake the quiz after uploading complete lecture PDFs.")
            out_rows.append(row)
            save_rows.append({**row, "source_trace": [], "retrieval_trace": []})
            continue

        weak_rel = np.array(
            [_chunk_weak_topic_relevance(chunks[i], topic, expansion_terms) for i in range(len(chunks))],
            dtype=np.float64,
        )
        exam_w = np.array(
            [_exam_relevance_weight(chunks[i], expansion_terms) for i in range(len(chunks))],
            dtype=np.float64,
        )
        gate = 0.55 * weak_rel + 0.45 * sim_scores
        discard = gate < MIN_COMBINED_GATE
        final_scores = (
            0.50 * weak_rel + 0.35 * sim_scores + 0.15 * exam_w
        )
        final_scores = np.where(discard, -1.0, final_scores)

        candidate_idx = np.argsort(final_scores)[::-1][: max(TOP_K_CHUNKS * LA_CANDIDATE_MULTIPLIER, 8)]
        candidate_idx = np.array(
            [i for i in candidate_idx.flatten().tolist() if final_scores[int(i)] >= 0],
            dtype=int,
        )
        if candidate_idx.size == 0:
            row = _strict_summary_row(topic, INSUFFICIENT_MESSAGE, [], [], "No lecture chunks passed weak-topic relevance gates.")
            out_rows.append(row)
            save_rows.append({**row, "source_trace": [], "retrieval_trace": []})
            continue

        candidate_idx = np.array(_deduplicate_ranked_indices(candidate_idx, chunks), dtype=int)
        if candidate_idx.size == 0:
            row = _strict_summary_row(topic, INSUFFICIENT_MESSAGE, [], [], "No deduplicated chunks available.")
            out_rows.append(row)
            save_rows.append({**row, "source_trace": [], "retrieval_trace": []})
            continue

        importance_scores = np.array(
            [_high_information_rank(_clean_chunk_text(chunks[int(i)]["text"]), topic) for i in candidate_idx],
            dtype=np.float64,
        )
        candidate_scores = np.array([final_scores[int(i)] for i in candidate_idx], dtype=np.float64)
        rerank_scores = 0.75 * candidate_scores + 0.25 * importance_scores
        sort_order = np.argsort(rerank_scores)[::-1]
        candidate_idx = candidate_idx[sort_order]

        cand_texts = [chunks[int(i)]["text"] for i in candidate_idx]
        cand_vecs = chunk_embs[candidate_idx]
        chosen_texts = _mmr_select(q_vec, cand_vecs, cand_texts, k=min(TOP_K_CHUNKS, len(cand_texts)), lam=0.75)
        chosen_set = set(chosen_texts)
        selected_rows: List[Tuple[int, Dict[str, Any]]] = []
        for i in candidate_idx:
            ch = chunks[int(i)]
            if ch["text"] in chosen_set:
                selected_rows.append((int(i), ch))
        selected_rows = selected_rows[:TOP_K_CHUNKS]

        snippets: List[str] = []
        source_trace: List[Dict[str, Any]] = []
        retrieval_trace: List[Dict[str, Any]] = []
        for idx, ch in selected_rows:
            txt = _clean_chunk_text(ch.get("text", ""))
            if not txt:
                continue
            wr = _chunk_weak_topic_relevance(ch, topic, expansion_terms)
            sv = float(sim_scores[idx]) if idx < len(sim_scores) else 0.0
            if wr < MIN_WEAK_TOPIC_RELEVANCE and sv < MIN_EMBEDDING_SIM_WEAK:
                continue
            snippet = _shorten_sentence(txt, 180)
            snippets.append(snippet)
            sim_val = float(sim_scores[idx]) if idx < len(sim_scores) else 0.0
            final_val = float(final_scores[idx]) if idx < len(final_scores) else 0.0
            source_trace.append(
                {
                    "lecture_id": ch.get("lecture_id", ""),
                    "lecture_name": ch.get("lecture_name", ch.get("lecture_id", "")),
                    "chunk_id": ch.get("chunk_id", ""),
                    "similarity_score": round(sim_val, 4),
                    "used_text_snippet": snippet,
                }
            )
            retrieval_trace.append(
                {
                    "lecture_id": ch.get("lecture_id", ""),
                    "lecture_name": ch.get("lecture_name", ch.get("lecture_id", "")),
                    "chunk_id": ch.get("chunk_id", ""),
                    "score": round(final_val, 4),
                    "similarity_score": round(sim_val, 4),
                    "embedding_similarity": round(sim_val, 4),
                    "weak_topic_relevance": round(float(wr), 4),
                }
            )

        snippets = _merge_overlapping_snippets(snippets)
        if not snippets:
            row = _strict_summary_row(topic, INSUFFICIENT_MESSAGE, [], [], "No chunks remained after weak-topic grounding filters.")
            out_rows.append(row)
            save_rows.append({**row, "source_trace": [], "retrieval_trace": []})
            continue

        notes_core = _lecture_grounded_notes(topic, snippets)
        llm_row = _llm_guidance_if_available(topic, [x[1] for x in selected_rows], topic_performance=topic_perf)
        grounded_llm = _ground_llm_notes(llm_row, snippets) if llm_row else {}

        if grounded_llm:
            gn = grounded_llm.get("revision_notes") or {}
            simple = str(grounded_llm.get("simple_explanation") or gn.get("concept_definition") or "").strip()
            kps = list(gn.get("key_points") or [])[:8]
            cms = list(gn.get("common_mistakes") or [])[:6]
            nxt = str(grounded_llm.get("next_action") or (gn.get("quick_revision_checklist") or [""])[0] or "").strip()
            if not simple or not _grounded_text(simple, snippets):
                notes_core = _lecture_grounded_notes(topic, snippets)
                if notes_core:
                    row = _strict_summary_row(
                        topic,
                        notes_core["concept_definition"],
                        notes_core["key_points"],
                        notes_core["common_mistakes"],
                        notes_core["quick_revision_checklist"][0],
                    )
                else:
                    row = _strict_summary_row(topic, INSUFFICIENT_MESSAGE, [], [], "Expand lecture coverage for this topic.")
            else:
                row = _strict_summary_row(topic, simple, kps, cms, nxt or "Review the retrieved lecture excerpts.")
        elif notes_core:
            row = _strict_summary_row(
                topic,
                notes_core["concept_definition"],
                notes_core["key_points"],
                notes_core["common_mistakes"],
                notes_core["quick_revision_checklist"][0],
            )
        else:
            row = _strict_summary_row(topic, INSUFFICIENT_MESSAGE, [], [], "Could not build lecture-only summary.")

        out_rows.append(row)
        save_rows.append({**row, "source_trace": source_trace, "retrieval_trace": retrieval_trace})

    if not out_rows:
        return {"weak_topic_summary": []}
    _save_outputs(save_rows)
    return {"weak_topic_summary": out_rows}

