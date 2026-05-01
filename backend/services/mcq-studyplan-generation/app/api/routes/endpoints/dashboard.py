"""Dashboard and analysis endpoints."""
import asyncio
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Service root in path
SERVICE_ROOT = Path(__file__).resolve().parents[4]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi import APIRouter
from app.services import state
from app.services.mcq_service import run_analysis
from topic_labels import clean_topic_display_name

router = APIRouter()

_ANALYSIS_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mcq_analysis")


def _normalize_topic_label(topic: str) -> str:
    raw = " ".join(str(topic or "").strip().split())
    if not raw:
        return ""
    return clean_topic_display_name(raw)


def _build_topic_analytics() -> dict:
    lecture_topic_breakdown = []
    global_topic_keys = set()
    global_unique_topics = []
    total_topics = 0

    for lec in state.LECTURE_DATA:
        lec_id = str(lec.get("id", ""))
        lec_name = str(lec.get("filename") or lec.get("file") or lec.get("title") or f"Lecture {lec_id}")
        # Keep analytics consistent with the dashboard "Top Topics" table.
        topics = [_normalize_topic_label(x) for x in _extract_top_topics(lec, limit=5)]
        topics = [x for x in topics if x]
        seen_local = set()
        dedup_topics = []
        for topic_label in topics:
            key = topic_label.lower()
            if key in seen_local:
                continue
            seen_local.add(key)
            dedup_topics.append(topic_label)
            if key not in global_topic_keys:
                global_topic_keys.add(key)
                global_unique_topics.append(topic_label)

        lecture_topic_breakdown.append(
            {
                "lecture_id": lec_id,
                "lecture_name": lec_name,
                "topics": dedup_topics,
                "topic_count": len(dedup_topics),
            }
        )
        total_topics += len(dedup_topics)

    # If lecture_data topics are unavailable, fall back to ALL_TOPICS grouping.
    if total_topics == 0 and state.ALL_TOPICS:
        by_lecture = {}
        for item in state.ALL_TOPICS:
            lid = str(item.get("lecture_id", ""))
            by_lecture.setdefault(lid, {"topics": [], "seen": set()})
            t = item.get("topic") or {}
            kws = [str(k).strip() for k in (t.get("keywords") or []) if str(k).strip()]
            topic_label = _normalize_topic_label(kws[0] if kws else str(t.get("rep_sentence") or ""))
            if not topic_label:
                continue
            key = topic_label.lower()
            if key in by_lecture[lid]["seen"]:
                continue
            by_lecture[lid]["seen"].add(key)
            by_lecture[lid]["topics"].append(topic_label)
            if key not in global_topic_keys:
                global_topic_keys.add(key)
                global_unique_topics.append(topic_label)

        lecture_topic_breakdown = []
        total_topics = 0
        for lec in state.LECTURE_DATA:
            lid = str(lec.get("id", ""))
            lec_name = str(lec.get("filename") or lec.get("file") or lec.get("title") or f"Lecture {lid}")
            topics = list((by_lecture.get(lid) or {}).get("topics") or [])
            lecture_topic_breakdown.append(
                {
                    "lecture_id": lid,
                    "lecture_name": lec_name,
                    "topics": topics,
                    "topic_count": len(topics),
                }
            )
            total_topics += len(topics)

    return {
        "total_topics": total_topics,
        "global_unique_topics": global_unique_topics,
        "unique_topics_count": len(global_unique_topics),
        "lecture_topic_breakdown": lecture_topic_breakdown,
    }


def _enrich_percentage_records(records: list) -> list:
    """Attach cleaned Top_Topics to distribution rows (same as /lecture-distribution)."""
    by_filename = {}
    for lec in state.LECTURE_DATA:
        filename = lec.get("filename")
        if filename:
            by_filename[filename] = lec
    for row in records:
        lec = by_filename.get(row.get("Lecture_File"))
        row["Top_Topics"] = _extract_top_topics(lec, limit=5) if lec else []
    return records


_NOISE_TOKENS = {
    "cid", "sid", "pid", "uid", "id", "ids",
    "dbi", "db", "sql", "table", "tables", "data", "value", "values",
    "field", "fields", "column", "columns", "row", "rows",
    "record", "records", "item", "items", "type", "types",
    "using", "used", "use", "example", "examples", "chapter", "topic",
    "just", "also", "new", "like", "may", "one", "two", "way",
}

_GENERIC_STOP = {
    "age", "contains", "contain", "access", "name", "names",
    "student", "students", "year", "years", "date", "dates", "time",
    "slide", "slides", "page", "section", "file", "files", "user", "users",
    "department", "course", "lecture", "notes",
}

_DATASET_HINTS = (
    "adventureworks", "northwind", "sakila", "contoso", "wide world",
    "imdb", "works2012", "2012", "2008",
)


def _normalize_token(text: str) -> str:
    val = (text or "").strip().lower().replace("_", " ").replace("-", " ")
    val = " ".join(val.split())
    return val


def _reject_keyword_token(token: str) -> bool:
    if not token or len(token) < 3:
        return True
    if len(token) > 24:
        return True
    if token in _NOISE_TOKENS or token in _GENERIC_STOP:
        return True
    if token.isdigit() or token.endswith(" id") or token.endswith("_id"):
        return True
    if re.search(r"\d", token):
        if token not in {"1nf", "2nf", "3nf", "bcnf"}:
            return True
    if re.match(r"^[a-z]+\d{3,}$", token):
        return True
    for hint in _DATASET_HINTS:
        if hint in token:
            return True
    return False


def _tokens_for_lecture(lecture: dict) -> set[str]:
    tokens: set[str] = set()
    for topic in (lecture.get("topics") or []):
        for kw in (topic.get("keywords") or []):
            token = _normalize_token(str(kw))
            if _reject_keyword_token(token):
                continue
            tokens.add(token)
    return tokens


def _tokens_from_mcq_context(lecture: dict) -> set[str]:
    tokens: set[str] = set()
    if not lecture or state.MCQ_DF.empty:
        return tokens
    lecture_id = lecture.get("id")
    if lecture_id is None or "lecture_id" not in state.MCQ_DF.columns:
        return tokens
    rows = state.MCQ_DF[state.MCQ_DF["lecture_id"] == lecture_id]
    if rows.empty:
        return tokens
    cols = [c for c in ("question", "question_text", "explanation", "rationale") if c in rows.columns]
    if not cols:
        return tokens
    for _, row in rows[cols].fillna("").iterrows():
        text = " ".join(str(row[c]) for c in cols)
        for tok in re.findall(r"[A-Za-z][A-Za-z0-9_\\-]{2,}", text.lower()):
            norm = _normalize_token(tok)
            if _reject_keyword_token(norm):
                continue
            tokens.add(norm)
    return tokens


def _has_any(tokens: set[str], words: set[str]) -> bool:
    return any(w in tokens for w in words)


def _extract_top_topics(lecture: dict, limit: int = 5) -> list[str]:
    """Return up to 5 DBMS concept labels; rule-based and MCQ-aligned."""
    if not lecture:
        return []

    lecture_tokens = _tokens_for_lecture(lecture)
    mcq_tokens = _tokens_from_mcq_context(lecture)
    tokens = lecture_tokens | mcq_tokens
    labels: list[str] = []

    def add_if(condition: bool, label: str) -> None:
        if condition and label not in labels and len(labels) < limit:
            labels.append(label)

    add_if(
        "jdbc" in tokens or "odbc" in tokens or "datasource" in tokens
        or ("driver" in tokens and _has_any(tokens, {"sql", "jdbc", "odbc", "database"})),
        "JDBC / Database Connectivity",
    )
    add_if(
        (("login" in tokens) and ("server" in tokens))
        or _has_any(tokens, {"authentication", "authorization"})
        or ("connection" in tokens and "database" in tokens),
        "Database Access",
    )
    add_if(
        _has_any(tokens, {"view", "views", "trigger", "triggers"}),
        "Views and Triggers",
    )
    add_if(
        _has_any(tokens, {"role", "roles", "privilege", "privileges", "grant", "grants", "revoke"}),
        "Roles and Privileges",
    )
    add_if(
        _has_any(tokens, {"backup", "backups", "recovery", "restore"}),
        "Backup and Recovery",
    )
    add_if(
        ("group" in tokens or "group by" in tokens)
        and _has_any(tokens, {"count", "sum", "avg", "average", "aggregate", "aggregation"}),
        "Aggregation (GROUP BY)",
    )
    add_if(
        _has_any(tokens, {"join", "joins", "inner join", "left join", "right join", "outer join"}),
        "SQL Joins",
    )
    add_if(
        _has_any(tokens, {"normalization", "1nf", "2nf", "3nf", "bcnf"}),
        "Normalization",
    )
    add_if(
        ("primary" in tokens and "key" in tokens)
        or ("foreign" in tokens and "key" in tokens)
        or ("candidate" in tokens and "key" in tokens)
        or _has_any(tokens, {"constraints", "constraint", "superkey", "alternate"}),
        "Keys and Constraints",
    )
    add_if(
        _has_any(tokens, {"transaction", "transactions", "commit", "rollback", "acid"}),
        "Transactions and ACID",
    )
    add_if(
        _has_any(tokens, {"index", "indexes", "indexing", "b tree", "hash index"}),
        "Indexing and Performance",
    )
    add_if(
        _has_any(tokens, {"er model", "erd", "entity model", "weak entity"})
        or ("weak" in tokens and "entity" in tokens),
        "ER Modeling",
    )
    add_if(
        (
            _has_any(tokens, {"entity", "entities"})
            and _has_any(tokens, {"relationship", "relationships"})
        )
        or (("faculty" in tokens) and ("member" in tokens)),
        "Entity Relationships",
    )

    return [clean_topic_display_name(lbl) for lbl in labels[:limit]]


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=True)
async def health():
    """Health check."""
    return {"status": "ok", "service": "mcq-study-plan"}


@router.get("/stats", include_in_schema=True)
async def get_stats():
    """Dashboard stats for React."""
    pct_df = state.PERCENTAGE_DF
    total_lectures = len(state.LECTURE_DATA)
    total_questions = len(state.MCQ_DF) if not state.MCQ_DF.empty else 0
    topic_analytics = _build_topic_analytics()
    high_priority = len(pct_df[pct_df["Percentage_of_Total"] > 10]) if not pct_df.empty else 0
    avg_per_lecture = round(total_questions / total_lectures, 1) if total_lectures > 0 else 0
    return {
        "total_lectures": total_lectures,
        "total_questions": total_questions,
        "total_topics": topic_analytics["total_topics"],
        "global_unique_topics": topic_analytics["global_unique_topics"],
        "unique_topics_count": topic_analytics["unique_topics_count"],
        "lecture_topic_breakdown": topic_analytics["lecture_topic_breakdown"],
        "avg_questions_per_lecture": avg_per_lecture,
        "high_priority_lectures": high_priority,
        "study_completion_percentage": 0,
        "processed": state.PROCESSED,
    }


@router.post("/analyze", include_in_schema=True)
async def analyze():
    """Run analysis on lecture materials."""
    # run_analysis is CPU/IO heavy (PDFs, embeddings, graph build). Running it on the
    # event loop would block all other /api requests and cause gateway 504 cascades.
    loop = asyncio.get_running_loop()
    success, message = await loop.run_in_executor(_ANALYSIS_EXECUTOR, run_analysis)
    if not success:
        return {"success": False, "message": message}
    pct_df = state.PERCENTAGE_DF
    total_lectures = len(state.LECTURE_DATA)
    total_questions = len(state.MCQ_DF) if not state.MCQ_DF.empty else 0
    topic_analytics = _build_topic_analytics()
    high_priority = len(pct_df[pct_df["Percentage_of_Total"] > 10]) if not pct_df.empty else 0
    avg_per_lecture = round(total_questions / total_lectures, 1) if total_lectures > 0 else 0
    return {
        "success": True,
        "message": message,
        "stats": {
            "total_lectures": total_lectures,
            "total_questions": total_questions,
            "total_topics": topic_analytics["total_topics"],
            "global_unique_topics": topic_analytics["global_unique_topics"],
            "unique_topics_count": topic_analytics["unique_topics_count"],
            "lecture_topic_breakdown": topic_analytics["lecture_topic_breakdown"],
            "avg_questions_per_lecture": avg_per_lecture,
            "high_priority_lectures": high_priority,
            "study_completion_percentage": 0,
            "processed": True,
        },
        "question_distribution_count": len(pct_df) if not pct_df.empty else 0,
        "total_lectures": total_lectures,
        "total_questions": total_questions,
        "percentage_df": _enrich_percentage_records(pct_df.to_dict("records")) if not pct_df.empty else [],
    }


@router.get("/lecture-distribution", include_in_schema=True)
async def list_lecture_distribution():
    """Lecture distribution data for charts."""
    if state.PERCENTAGE_DF.empty:
        return []
    records = state.PERCENTAGE_DF.to_dict("records")
    return _enrich_percentage_records(records)
