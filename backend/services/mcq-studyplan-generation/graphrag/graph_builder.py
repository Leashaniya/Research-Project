"""
Student-friendly graph construction helpers (labels, colors, topic–topic links).
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set, Tuple

from nlp_utils import shorten

# Student-facing palette (avoid jargon in labels; colors carry meaning)
COLOR_LECTURE = "#7E57C2"  # purple: lecture / source material
COLOR_TOPIC_WEAK = "#E53935"  # red
COLOR_TOPIC_STRONG = "#43A047"  # green
COLOR_TOPIC_PRIORITY = "#FB8C00"  # orange — important for exams
COLOR_TOPIC_NEUTRAL = "#78909C"  # gray-blue when no signal
COLOR_MCQ_RECOMMENDED = "#1E88E5"  # blue — suggested practice (from your PDFs)
COLOR_MCQ_OTHER = "#B0BEC5"  # light gray — other questions in bank
COLOR_EDGE_TOPIC_RELATED = "#B39DDB"
COLOR_EDGE_LECTURE = "#CE93D8"


def lecture_display_name(lecture: Dict[str, Any]) -> str:
    title = shorten(lecture.get("title") or "Lecture", 40)
    fn = os.path.basename(lecture.get("file", ""))
    return f"{title}" if not fn else f"{title}"


def lecture_tooltip(
    lecture: Dict[str, Any],
    band: str,
    accuracy_pct: Optional[float],
    is_priority: bool,
) -> str:
    fn = os.path.basename(lecture.get("file", ""))
    lines = [
        "<b>Your lecture</b>",
        lecture.get("title") or fn or "Lecture",
        f"<br><b>Source file</b><br>{fn}",
    ]
    if accuracy_pct is not None:
        lines.append(f"<br><b>Your recent quiz</b><br>{accuracy_pct:.0f}% correct")
    else:
        lines.append("<br><b>Your recent quiz</b><br>No quiz yet for this lecture")
    if band == "weak":
        lines.append("<br><span style='color:#c62828'><b>Focus here</b> — practice more</span>")
    elif band == "strong":
        lines.append("<br><span style='color:#2e7d32'><b>Strong area</b> — keep it up</span>")
    if is_priority:
        lines.append("<br><span style='color:#ef6c00'><b>Often examined</b> — high share of questions</span>")
    lines.append("<br><small>Purple = lecture material</small>")
    return "".join(lines)


def topic_tooltip(
    keywords: str,
    lecture_title: str,
    band: str,
    is_priority: bool,
    recommended_nearby: bool,
) -> str:
    lines = [
        "<b>Topic</b><br>",
        keywords,
        f"<br><br><b>From</b><br>{lecture_title}",
    ]
    if band == "weak":
        lines.append("<br><br><b>Why red</b><br>Linked to a lecture where your quiz score was lower")
    elif band == "strong":
        lines.append("<br><br><b>Why green</b><br>Linked to a lecture where you did well")
    elif is_priority:
        lines.append("<br><br><b>Why orange</b><br>High exam frequency — many questions from this area")
    else:
        lines.append("<br><br><b>Topic cluster</b><br>Main ideas from your slides")
    if recommended_nearby:
        lines.append("<br><br><b>Practice</b><br>See blue questions for suggested MCQs")
    return "".join(lines)


def mcq_tooltip(
    question_text: str,
    lecture_title: str,
    source_file: str,
    is_recommended: bool,
    reasons: Optional[List[str]] = None,
) -> str:
    q = (question_text or "")[:320]
    if len(question_text or "") > 320:
        q += "…"
    lines = [
        "<b>Question from your materials</b><br>",
        q,
        f"<br><br><b>Lecture</b><br>{lecture_title}",
        f"<br><b>Source</b><br>{source_file}",
    ]
    if is_recommended:
        lines.append("<br><br><b>Suggested for you</b>")
        if reasons:
            for r in reasons[:5]:
                lines.append(f"<br>• {r}")
        lines.append("<br><small>Blue = recommended practice MCQ</small>")
    else:
        lines.append("<br><small>Gray = other MCQ in your question bank</small>")
    return "".join(lines)


def topic_node_id(topic: Dict[str, Any], lecture_id: str) -> str:
    return f"topic_{topic.get('topic_id', 0)}_{lecture_id}"


def add_related_topic_edges(
    net: Any,
    lecture_data: List[Dict[str, Any]],
    max_edges: int = 100,
) -> int:
    """
    Link topics that share vocabulary (simple relational signal for students).
    Returns number of edges added.
    """
    nodes_meta: List[Tuple[str, str, Set[str]]] = []
    for lec in lecture_data:
        lid = lec["id"]
        for topic in lec.get("topics", []):
            tid = topic_node_id(topic, lid)
            kws = {k.lower() for k in topic.get("keywords", [])[:12] if k}
            if kws:
                nodes_meta.append((tid, lec.get("title", ""), kws))

    added = 0
    for i, (id_a, _, kws_a) in enumerate(nodes_meta):
        for id_b, _, kws_b in nodes_meta[i + 1 :]:
            if id_a == id_b:
                continue
            shared = kws_a & kws_b
            if not shared:
                continue
            net.add_edge(
                id_a,
                id_b,
                title="Related topic (shared ideas)",
                color=COLOR_EDGE_TOPIC_RELATED,
                width=1,
            )
            added += 1
            if added >= max_edges:
                return added
    return added
