"""Extract priority questions for quiz - used by FastAPI quiz endpoint."""
import os
import re
import random
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Tuple

from topic_labels import clean_topic_display_name

# Kept in sync with GraphRAG priority lecture count (top lectures by question share)
NUM_TOP_PRIORITY_LECTURES = 8
QUIZ_AUDIT_PATH = Path("outputs") / "quiz_audit.json"


def _normalize_text_tokens(text: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())
    return {tok for tok in cleaned.split() if len(tok) >= 3}


def _best_topic_for_question(question_text: str, options: List[str], lecture_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Lightweight topic mapping using existing extracted lecture topic keywords.
    No ML model added - simple keyword overlap scoring.
    """
    topics = lecture_info.get("topics") or []
    if not topics:
        return {"topic_name": "General", "topic_confidence": 0.0, "topic_match_method": "fallback"}

    question_blob = f"{question_text or ''} {' '.join(options or [])}"
    q_tokens = _normalize_text_tokens(question_blob)
    if not q_tokens:
        first_kw = (topics[0].get("keywords") or ["General"])[0]
        return {
            "topic_name": clean_topic_display_name(str(first_kw)),
            "topic_confidence": 0.0,
            "topic_match_method": "fallback",
        }

    best_label = None
    best_score = 0.0
    for t in topics:
        kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
        if not kws:
            continue
        topic_tokens = _normalize_text_tokens(" ".join(kws))
        if not topic_tokens:
            continue
        overlap = q_tokens & topic_tokens
        score = len(overlap) / max(1, len(topic_tokens))
        if score > best_score:
            best_score = score
            best_label = kws[0]

    if best_label and best_score > 0:
        return {
            "topic_name": clean_topic_display_name(str(best_label)),
            "topic_confidence": round(float(best_score), 3),
            "topic_match_method": "keyword_overlap",
        }

    first_kw = (topics[0].get("keywords") or ["General"])[0]
    return {
        "topic_name": clean_topic_display_name(str(first_kw)),
        "topic_confidence": 0.0,
        "topic_match_method": "fallback",
    }


def is_valid_mcq_question(question: dict) -> bool:
    """Check if a question has valid MCQ options, answer, and text."""
    if not question or not isinstance(question, dict):
        return False
    q_text = str(question.get("text", "")).strip()
    if not q_text:
        return False
    q_text_l = q_text.lower()
    if q_text_l.endswith(","):
        return False
    if "select one or more" in q_text_l:
        return False
    broken_question_fragments = (
        "select s",
        "relation r(a, b,",
        "create function dbo",
        "resultset rs = stmt",
        "consider relational schemes:",
        "consider r(a, b,",
    )
    if any(f in q_text_l for f in broken_question_fragments):
        return False
    # Reject likely truncated prompts.
    if len(q_text) < 25:
        return False
    if q_text.count("(") > q_text.count(")"):
        return False

    answer = str(question.get("answer", "")).strip()
    if not answer:
        return False
    answer_l = answer.lower()
    # Single-choice quiz only: reject multi-answer metadata.
    if re.search(r"\b[a-d]\s*[,/&]\s*[a-d]\b", answer_l) or " and " in answer_l:
        return False
    if not re.match(r"^[A-Da-d](?:[\.\)])?$", answer.strip()):
        return False

    options = question.get("options", [])
    if not options or len(options) < 2:
        return False

    norm_opts = []
    valid_option_count = sum(
        1 for opt in options if re.match(r"^[A-D][\.\)]", str(opt).strip())
    )
    if valid_option_count < 2:
        return False

    for opt in options:
        raw = str(opt).strip()
        if not raw:
            return False
        body = re.sub(r"^[A-Da-d][\.\)]\s*", "", raw).strip()
        body_l = body.lower()
        if len(body) < 2:
            return False
        # Reject incomplete / broken option fragments.
        if body_l in {"select s", "relation r(a, b,", "create function dbo", "resultset rs = stmt"}:
            return False
        if body.endswith(","):
            return False
        norm = re.sub(r"\s+", " ", body_l)
        norm_opts.append(norm)

    # Reject duplicate option text.
    if len(set(norm_opts)) != len(norm_opts):
        return False

    return True


def filter_valid_mcq_questions(questions: List[dict]) -> List[dict]:
    """Filter to only valid MCQ questions."""
    return [q for q in questions if is_valid_mcq_question(q)]


def _question_signature(question: dict) -> str:
    text = str(question.get("text", "")).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def _normalized_question_text(raw: str) -> str:
    text = str(raw or "").lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _write_quiz_audit(
    extracted_questions: List[Dict[str, Any]],
    requirements: Dict[str, int],
    fallback_usage: Dict[str, int],
    expected_total: int,
) -> None:
    lecture_distribution: Dict[str, int] = {}
    seen: set[str] = set()
    duplicate_count = 0

    for q in extracted_questions:
        lec = str(q.get("lecture", "unknown"))
        lecture_distribution[lec] = lecture_distribution.get(lec, 0) + 1
        norm_q = _normalized_question_text(q.get("question_text", ""))
        if norm_q in seen:
            duplicate_count += 1
        else:
            seen.add(norm_q)

    if duplicate_count > 0:
        print(f"[quiz_audit] warning: duplicate questions detected = {duplicate_count}")

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "expected_total_questions": int(expected_total),
        "generated_total_questions": int(len(extracted_questions)),
        "is_expected_total_met": len(extracted_questions) == int(expected_total),
        "lecture_distribution": lecture_distribution,
        "target_distribution": requirements,
        "duplicate_count": int(duplicate_count),
        "fallback_usage_count": fallback_usage,
    }

    try:
        QUIZ_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QUIZ_AUDIT_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass


def _topic_cluster_tokens(lecture_info: Dict[str, Any]) -> set[str]:
    toks = set()
    for t in (lecture_info.get("topics") or []):
        for kw in (t.get("keywords") or []):
            toks |= _normalize_text_tokens(str(kw))
    return toks


def _topic_labels_for_lecture(lecture_info: Dict[str, Any]) -> set[str]:
    labels = set()
    for t in (lecture_info.get("topics") or []):
        kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
        if kws:
            labels.add(clean_topic_display_name(kws[0]))
    return labels


def extract_questions_from_top_priorities(
    lecture_data: List[Dict[str, Any]],
    percentage_df,
    num_priorities: int = NUM_TOP_PRIORITY_LECTURES,
    total_questions: int = 44,
) -> List[Dict[str, Any]]:
    """Extract balanced quiz questions by lecture priority buckets.

    Target distribution:
    - Top 4 lectures (by Percentage_of_Total): 7 questions each
    - Next 4 lectures: 4 questions each
    Total: 44 questions across 8 lectures
    """
    if percentage_df.empty or not lecture_data:
        return []

    percentage_df = percentage_df.sort_values(
        "Percentage_of_Total", ascending=False
    ).reset_index(drop=True)
    ranked_rows = percentage_df.head(8).reset_index(drop=True)
    if ranked_rows.empty:
        return []

    from pdf_utils import extract_text_from_pdf
    from mcq_utils import extract_questions_from_pdf

    # Preload pools for selected lectures.
    lecture_entries: List[Dict[str, Any]] = []
    for rank_idx, row in ranked_rows.iterrows():
        lecture_file = row["Lecture_File"]
        lecture_info = next(
            (lec for lec in lecture_data if os.path.basename(lec["file"]) == lecture_file),
            None,
        )
        if not lecture_info or not lecture_info.get("question_file"):
            continue
        try:
            q_text = extract_text_from_pdf(lecture_info["question_file"])
            questions = extract_questions_from_pdf(q_text, use_openai_for_answers=False)
        except Exception as e:
            print(f"Error extracting questions from {lecture_info.get('question_file')}: {e}")
            questions = []

        valid = filter_valid_mcq_questions(questions)
        lecture_entries.append(
            {
                "rank": rank_idx + 1,
                "lecture_file": lecture_file,
                "lecture_info": lecture_info,
                "all_questions": questions,
                "valid_questions": valid,
                "cluster_tokens": _topic_cluster_tokens(lecture_info),
                "topic_labels": _topic_labels_for_lecture(lecture_info),
            }
        )

    if not lecture_entries:
        return []

    high_entries = lecture_entries[:4]
    low_entries = lecture_entries[4:8]

    # Target counts: 7 for top4, 4 for remaining4.
    requirements: Dict[str, int] = {}
    for e in high_entries:
        requirements[e["lecture_file"]] = 7
    for e in low_entries:
        requirements[e["lecture_file"]] = 4

    seen_questions: set[str] = set()
    extracted_questions: List[Dict[str, Any]] = []
    fallback_usage = {
        "same_lecture_topic_cluster": 0,
        "similar_topic_cross_lecture": 0,
        "last_resort_reuse": 0,
        "global_backfill_reuse": 0,
    }

    def _pick_from_pool(pool: List[dict], need: int, rng: random.Random) -> List[dict]:
        pool = list(pool)
        rng.shuffle(pool)
        selected: List[dict] = []
        local_seen: set[str] = set()
        for q in pool:
            if len(selected) >= need:
                break
            sig = _question_signature(q)
            if not sig:
                continue
            if sig in local_seen or sig in seen_questions:
                continue
            local_seen.add(sig)
            seen_questions.add(sig)
            selected.append(q)
        return selected

    def _same_topic_fallback(entry: Dict[str, Any], need: int, rng: random.Random) -> List[dict]:
        if need <= 0:
            return []
        target_labels = entry.get("topic_labels") or set()
        candidates: List[dict] = []
        # Strict fallback: same lecture pool only (no cross-lecture mixing).
        for q in entry.get("valid_questions") or []:
            topic_meta = _best_topic_for_question(
                q.get("text", ""),
                q.get("options") or [],
                entry.get("lecture_info") or {},
            )
            if topic_meta.get("topic_name") in target_labels:
                candidates.append(q)
        candidates = list(candidates)
        rng.shuffle(candidates)
        picked: List[dict] = []
        local_seen: set[str] = set()
        for q in candidates:
            if len(picked) >= need:
                break
            sig = _question_signature(q)
            if not sig or sig in local_seen or sig in seen_questions:
                continue
            local_seen.add(sig)
            seen_questions.add(sig)
            picked.append(q)
        return picked

    for entry in lecture_entries:
        lecture_file = entry["lecture_file"]
        needed = requirements.get(lecture_file, 0)
        if needed <= 0:
            continue
        seed_src = f"{lecture_file}|{entry.get('rank', 0)}|strict_lecture_sampling_v2"
        seed_val = int(hashlib.md5(seed_src.encode("utf-8")).hexdigest()[:8], 16)
        rng = random.Random(seed_val)

        # 1) Prefer valid MCQs from same lecture (diversity-aware).
        selected = _pick_from_pool(list(entry.get("valid_questions") or []), needed, rng)

        # 2) If short, continue from same lecture valid pool.
        if len(selected) < needed:
            more_needed = needed - len(selected)
            selected.extend(_pick_from_pool(list(entry.get("valid_questions") or []), more_needed, rng))

        # 3) If short, fallback to same-lecture topic-cluster questions only.
        if len(selected) < needed:
            more_needed = needed - len(selected)
            same_topic_selected = _same_topic_fallback(entry, more_needed, rng)
            fallback_usage["same_lecture_topic_cluster"] += len(same_topic_selected)
            selected.extend(same_topic_selected)

        rng.shuffle(selected)
        out_priority = int(entry["rank"])
        for i, q in enumerate(selected[:needed]):
            q_num = q.get("number", i + 1)
            lecture_info = entry["lecture_info"]
            topic_meta = _best_topic_for_question(
                q.get("text", ""),
                q.get("options") or [],
                lecture_info,
            )
            extracted_questions.append(
                {
                    "priority": out_priority,
                    "lecture": lecture_file,
                    "lecture_title": lecture_info["title"],
                    "question_number": q_num,
                    "question_text": q.get("text", ""),
                    "options": " | ".join(q["options"]) if q.get("options") else "",
                    "answer": q.get("answer", ""),
                    "total_questions_in_lecture": len(entry.get("all_questions") or []),
                    "topic_name": topic_meta["topic_name"],
                    "topic_confidence": topic_meta["topic_confidence"],
                    "topic_match_method": topic_meta["topic_match_method"],
                }
            )

    # Global fail-safe: keep requested total target using same-lecture backfill only.
    required_total = max(sum(requirements.values()), int(total_questions or 0))
    if len(extracted_questions) < required_total:
        by_lecture = {e["lecture_file"]: list(e.get("valid_questions") or []) for e in lecture_entries}
        for e in lecture_entries:
            lecture_file = e["lecture_file"]
            need = requirements.get(lecture_file, 0)
            have = sum(1 for r in extracted_questions if r.get("lecture") == lecture_file)
            short = max(0, need - have)
            pool = by_lecture.get(lecture_file) or []
            seed_src = f"{lecture_file}|global_backfill|strict_lecture_sampling_v2"
            seed_val = int(hashlib.md5(seed_src.encode("utf-8")).hexdigest()[:8], 16)
            rng = random.Random(seed_val)
            while short > 0 and pool:
                picked = _pick_from_pool(pool, 1, rng)
                if not picked:
                    break
                q = picked[0]
                q_num = q.get("number", short)
                topic_meta = _best_topic_for_question(
                    q.get("text", ""),
                    q.get("options") or [],
                    e["lecture_info"],
                )
                extracted_questions.append(
                    {
                        "priority": min(int(e["rank"]), 4),
                        "lecture": lecture_file,
                        "lecture_title": e["lecture_info"]["title"],
                        "question_number": q_num,
                        "question_text": q.get("text", ""),
                        "options": " | ".join(q["options"]) if q.get("options") else "",
                        "answer": q.get("answer", ""),
                        "total_questions_in_lecture": len(e.get("all_questions") or []),
                        "topic_name": topic_meta["topic_name"],
                        "topic_confidence": topic_meta["topic_confidence"],
                        "topic_match_method": topic_meta["topic_match_method"],
                    }
                )
                short -= 1
                fallback_usage["global_backfill_reuse"] += 1
            if len(extracted_questions) >= required_total:
                break

    if len(extracted_questions) > required_total:
        extracted_questions = extracted_questions[:required_total]

    final_questions = extracted_questions
    print(f"[quiz_generation] total_final_questions={len(final_questions)}")
    print(f"[quiz_generation] total_quiz_questions={len(final_questions)}")

    lecture_breakdown: Dict[str, int] = {}
    for q in extracted_questions:
        lec = str(q.get("lecture", "unknown"))
        lecture_breakdown[lec] = lecture_breakdown.get(lec, 0) + 1
    print(f"[quiz_generation] lecture_breakdown={lecture_breakdown}")
    print(f"[quiz_generation] selected_count_by_lecture={lecture_breakdown}")

    # Post-generation audit/report layer (non-breaking, output-only).
    _write_quiz_audit(
        extracted_questions=final_questions,
        requirements=requirements,
        fallback_usage=fallback_usage,
        expected_total=required_total,
    )

    return final_questions
