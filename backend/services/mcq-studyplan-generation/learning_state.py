"""Shared learning-state layer used by RAG and GraphRAG.

RAG and GraphRAG remain separate modules and only communicate through this state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_PATH = Path("outputs") / "learning_state.json"
DEFAULT_STUDENT_ID = "default_student"


def _default_student_state() -> Dict[str, Any]:
    return {
        "weak_topics": [],
        "strong_topics": [],
        "mastered_topics": [],
        "quiz_history": [],
        "confidence_score": {},
        "updated_at": "",
    }


def _load_store(path: Optional[Path] = None) -> Dict[str, Any]:
    p = path or STATE_PATH
    if not p.exists():
        return {"students": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw = json.load(f) or {}
        students = raw.get("students")
        if not isinstance(students, dict):
            return {"students": {}}
        return {"students": students}
    except (OSError, json.JSONDecodeError):
        return {"students": {}}


def _save_store(store: Dict[str, Any], path: Optional[Path] = None) -> None:
    p = path or STATE_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2)
    except OSError:
        pass


def get_learning_state(student_id: str = DEFAULT_STUDENT_ID) -> Dict[str, Any]:
    store = _load_store()
    row = (store.get("students") or {}).get(student_id) or {}
    base = _default_student_state()
    base.update({k: v for k, v in row.items() if k in base})
    return base


def _topic_confidence(total: int, accuracy_pct: float) -> float:
    # Confidence mixes evidence size + performance quality, clamped to [0,1].
    evidence = min(1.0, max(0.0, float(total) / 5.0))
    quality = min(1.0, max(0.0, float(accuracy_pct) / 100.0))
    return round((0.45 * evidence) + (0.55 * quality), 4)


def update_learning_state_after_quiz(
    quiz_results: Dict[str, Any],
    graph_weak_topics: Optional[List[str]] = None,
    student_id: str = DEFAULT_STUDENT_ID,
) -> Dict[str, Any]:
    store = _load_store()
    students = store.setdefault("students", {})
    current = students.get(student_id) or _default_student_state()

    topic_rows = quiz_results.get("topic_wise_accuracy") or {}
    confidence: Dict[str, float] = dict(current.get("confidence_score") or {})
    strong_topics: List[str] = []
    mastered_topics: List[str] = []
    for topic_name, row in topic_rows.items():
        topic = str(topic_name).strip()
        if not topic:
            continue
        total = int((row or {}).get("total", 0) or 0)
        acc = float((row or {}).get("accuracy", 0.0) or 0.0)
        conf = _topic_confidence(total=total, accuracy_pct=acc)
        confidence[topic] = conf
        band = str((row or {}).get("band", "moderate")).strip().lower()
        reliable = bool((row or {}).get("is_reliable", False))
        if band == "strong":
            strong_topics.append(topic)
            if reliable and conf >= 0.78:
                mastered_topics.append(topic)

    graph_weak_topics = [str(t).strip() for t in (graph_weak_topics or []) if str(t).strip()]
    weak_topics = list(dict.fromkeys(graph_weak_topics)) if graph_weak_topics else list(
        dict.fromkeys(current.get("weak_topics") or [])
    )

    attempt = {
        "attempted_at": datetime.now(timezone.utc).isoformat(),
        "total_attempted": int(quiz_results.get("total_attempted", 0) or 0),
        "correct_count": int(quiz_results.get("correct_count", 0) or 0),
        "wrong_count": int(quiz_results.get("wrong_count", 0) or 0),
        "accuracy": float(quiz_results.get("accuracy", 0.0) or 0.0),
        "weak_topics": weak_topics,
    }
    quiz_history = list(current.get("quiz_history") or [])
    quiz_history.append(attempt)
    quiz_history = quiz_history[-30:]

    next_state = {
        "weak_topics": weak_topics,
        "strong_topics": list(dict.fromkeys(strong_topics)),
        "mastered_topics": list(dict.fromkeys(mastered_topics)),
        "quiz_history": quiz_history,
        "confidence_score": confidence,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    students[student_id] = next_state
    _save_store(store)
    return next_state

