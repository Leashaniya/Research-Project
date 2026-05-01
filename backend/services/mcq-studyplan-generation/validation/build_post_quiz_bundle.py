"""Build a consolidated post-quiz bundle from existing outputs.

Non-invasive helper:
- does not modify quiz generation, GraphRAG scoring, or adaptive planning logic
- only reads existing artifacts and writes a combined JSON report
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUTS = BASE_DIR / "outputs"
QUIZ_STATE = OUTPUTS / "graphrag_quiz_state.json"
RECS = OUTPUTS / "graphrag_recommendations.json"
ADAPTIVE = OUTPUTS / "adaptive_study_plan.csv"
OUT = OUTPUTS / "post_quiz_bundle.json"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _risk_label(topic: str, weak_set: set[str], high_lectures: set[str]) -> str:
    if topic in weak_set:
        # If weak topic belongs to top4 context in rec traces, mark high-risk.
        if any(h in topic.lower() for h in high_lectures):
            return "high-risk"
        return "moderate-risk"
    return "monitor"


def main() -> None:
    quiz = _load_json(QUIZ_STATE)
    recs_payload = _load_json(RECS)
    recs = list(recs_payload.get("recommendations") or [])
    rec_meta = recs_payload.get("meta") or {}

    weak_topics = [str(t).strip() for t in (quiz.get("weak_topics_confirmed") or []) if str(t).strip()]
    weak_set = {w.lower() for w in weak_topics}

    high_priority_lectures = set(str(x).lower() for x in (rec_meta.get("priority_files") or [])[:4])

    weak_topic_nodes: List[Dict[str, Any]] = []
    topic_acc = quiz.get("topic_wise_accuracy") or {}
    for wt in weak_topics:
        row = topic_acc.get(wt) or {}
        weak_topic_nodes.append(
            {
                "topic_name": wt,
                "accuracy": float(row.get("accuracy", 0.0)),
                "risk_band": _risk_label(wt.lower(), weak_set, high_priority_lectures),
            }
        )

    recommended_mcqs = []
    for r in recs[:20]:
        trace = r.get("reason_trace") or {}
        recommended_mcqs.append(
            {
                "rank": int(trace.get("recommendation_rank", 0) or 0),
                "question_id": r.get("question_id", ""),
                "weak_topic": trace.get("supports_weak_topic", ""),
                "related_concept": trace.get("related_concept", ""),
                "prerequisite_topics": trace.get("prerequisite_path", []) or [],
                "supporting_lecture_group": "high-priority"
                if str(r.get("question_id", "")).lower().startswith("lec_2")
                else "medium/low-priority",
            }
        )

    adaptive_rows = []
    if ADAPTIVE.exists():
        try:
            df = pd.read_csv(ADAPTIVE)
        except Exception:
            df = pd.DataFrame()
        for _, row in df.iterrows():
            adaptive_rows.append(
                {
                    "lecture": row.get("Lecture", ""),
                    "quiz_accuracy": row.get("Quiz_Accuracy", ""),
                    "adaptive_hours": float(row.get("Adaptive_Hours", 0.0) or 0.0),
                    "focus_intensity": row.get("Focus_Intensity", ""),
                    "study_focus": row.get("Study_Focus", ""),
                }
            )

    # weak -> medium -> strong ordering for bundle view
    def _priority_key(item: Dict[str, Any]) -> int:
        label = str(item.get("focus_intensity", "")).lower()
        if "high" in label or "needs focus" in label:
            return 0
        if "medium" in label or "review" in label:
            return 1
        return 2

    adaptive_rows.sort(key=_priority_key)

    bundle = {
        "weak_topics": weak_topic_nodes,
        "recommended_mcqs": recommended_mcqs,
        "adaptive_study_plan": adaptive_rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"[post_quiz_bundle] wrote {OUT}")


if __name__ == "__main__":
    main()

