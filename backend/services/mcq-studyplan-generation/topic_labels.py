"""
Human-readable topic labels for API responses and student-facing views.
Maps noisy extraction tokens to consistent display names (no core logic changes).
"""
from __future__ import annotations

import re
from typing import Optional

# Longer phrases first for substring-style checks
_PHRASE_MAP: tuple[tuple[str, str], ...] = (
    ("faculty member", "ER Modeling"),
    ("group by", "Aggregation (GROUP BY, COUNT, SUM)"),
    ("entity relationship", "Entity Relationships"),
    ("entity relationships", "Entity Relationships"),
)

# Must match rule-based labels from dashboard._extract_top_topics (lowercase keys)
_CURATED_FROM_ANALYSIS: dict[str, str] = {
    "jdbc": "JDBC / Database Connectivity",
    "jdbc / database connectivity": "JDBC / Database Connectivity",
    "database access": "Database Access",
    "views and triggers": "Views and Triggers",
    "roles and privileges": "Roles and Privileges",
    "backup and recovery": "Backup and Recovery",
    "sql joins": "SQL Joins",
    "normalization": "Normalization",
    "keys and constraints": "Keys and Constraints",
    "transactions and acid": "Transactions and ACID",
    "indexing and performance": "Indexing and Performance",
    "er modeling": "ER Modeling",
    "entity relationships": "Entity Relationships",
}

_TOKEN_MAP: dict[str, str] = {
    "jdbc": "JDBC / Database Connectivity",
    "group": "Aggregation (GROUP BY, COUNT, SUM)",
    "groups": "Aggregation (GROUP BY, COUNT, SUM)",
    "aggregation": "Aggregation (GROUP BY, COUNT, SUM)",
    "aggregate": "Aggregation (GROUP BY, COUNT, SUM)",
    "sql": "SQL Queries",
    "relation": "Entity Relationships",
    "relations": "Entity Relationships",
    "relational": "Entity Relationships",
    "eid": "Entity Attributes",
    "server": "Database Server",
    "login": "Authentication",
    "views": "Views",
    "view": "Views",
    "trigger": "Triggers",
    "triggers": "Triggers",
    "security": "Database Security",
    "general": "General",
}


def _normalize_key(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"[_\-]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def clean_topic_display_name(raw: Optional[str]) -> str:
    """Return a clean, student-facing topic label."""
    if raw is None:
        return "General"
    s = str(raw).strip()
    if not s:
        return "General"

    key = _normalize_key(s)
    if key in _CURATED_FROM_ANALYSIS:
        return _CURATED_FROM_ANALYSIS[key]

    for phrase, label in _PHRASE_MAP:
        if phrase in key:
            return label

    if key in _TOKEN_MAP:
        return _TOKEN_MAP[key]

    # Title-case short tokens (e.g. leftover single words)
    words = key.split()
    if len(words) <= 4 and all(w.isalpha() for w in words):
        return " ".join(w.capitalize() for w in words)

    return s if s[0].isupper() else s.capitalize()


def clean_topic_keyword_chip(raw: Optional[str]) -> str:
    """Clean a single keyword for graph chips; keeps very short output."""
    label = clean_topic_display_name(raw)
    if len(label) > 48:
        return label[:45] + "..."
    return label
