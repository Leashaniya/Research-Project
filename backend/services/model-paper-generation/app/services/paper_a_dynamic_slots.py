"""
Paper A: infer num_slots from recent past papers using the MODE of question counts.

Uses PDF filenames with a 20xx year; loads cached blueprints under text_extraction_hybrid/<stem>/.
The mode is the count that appears most often (e.g. [4,4,4,5,6] -> 4).
Ties: if multiple values share the highest frequency, the smallest count is chosen (deterministic).
"""
from __future__ import annotations

import json
import logging
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.core.paths import PAST_PAPERS_DIR, TEXT_EXTRACTION_DIR

logger = logging.getLogger(__name__)

MIN_SLOTS = 1
MAX_SLOTS = 8
DEFAULT_FALLBACK_SLOTS = 4
RECENT_YEARS_WINDOW = 6


def _parse_year_from_filename(filename: str) -> Optional[int]:
    m = re.search(r"(20\d{2})", str(filename or ""))
    return int(m.group(1)) if m else None


def _count_questions_in_blueprint_data(data: Any) -> Optional[int]:
    if isinstance(data, list):
        return len(data) if data else 0
    if isinstance(data, dict):
        qs = data.get("questions")
        if isinstance(qs, list):
            return len(qs)
    return None


def _count_questions_for_pdf_stem(stem: str, base_dir: Path) -> Optional[int]:
    if not stem:
        return None
    fp_sub = base_dir / stem / "blueprint_with_subquestions.json"
    fp_main = base_dir / stem / "blueprint.json"
    fp = fp_sub if fp_sub.exists() else fp_main if fp_main.exists() else None
    if not fp:
        return None
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except Exception as e:
        logger.debug("Could not read blueprint %s: %s", fp, e)
        return None
    return _count_questions_in_blueprint_data(data)


def _mode_question_count(counts: List[int]) -> Tuple[int, Dict[str, Any]]:
    """
    Statistical mode: value with highest frequency.
    Multimodal tie: choose the smallest count (deterministic for exams).
    """
    if not counts:
        raise ValueError("counts must be non-empty")
    ctr = Counter(counts)
    max_freq = max(ctr.values())
    candidates = sorted([k for k, v in ctr.items() if v == max_freq])
    chosen = candidates[0]
    detail = {
        "mode": chosen,
        "mode_frequency": max_freq,
        "mode_candidates": candidates,
        "multimodal_tie": len(candidates) > 1,
        "count_distribution": dict(sorted(ctr.items())),
    }
    return chosen, detail


def compute_paper_a_num_slots_from_recent_papers(
    *,
    years_window: int = RECENT_YEARS_WINDOW,
    fallback: int = DEFAULT_FALLBACK_SLOTS,
    min_slots: int = MIN_SLOTS,
    max_slots: int = MAX_SLOTS,
    past_papers_dir: Optional[Path] = None,
    text_extraction_dir: Optional[Path] = None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Over past papers in the last `years_window` calendar years (inclusive of current year),
    collect each paper's top-level question count from cached blueprints, then take the MODE.
    Result is clamped to [min_slots, max_slots].
    """
    pp_dir = Path(past_papers_dir or PAST_PAPERS_DIR)
    base_dir = Path(text_extraction_dir or TEXT_EXTRACTION_DIR)

    current_year = datetime.now().year
    min_year = current_year - (int(years_window) - 1)

    meta: Dict[str, Any] = {
        "strategy": "mode_question_count_recent_papers",
        "years_window": years_window,
        "year_range_inclusive": [min_year, current_year],
        "papers_in_window": 0,
        "papers_with_blueprint": 0,
        "question_counts": [],
        "mode": None,
        "mode_frequency": None,
        "mode_candidates": [],
        "multimodal_tie": False,
        "count_distribution": {},
        "num_slots": fallback,
        "fallback_used": True,
        "fallback_reason": None,
    }

    if not pp_dir.exists():
        meta["fallback_reason"] = "past_papers_dir_missing"
        return fallback, meta

    all_pdfs = sorted(
        [p.name for p in pp_dir.glob("*.pdf")] + [p.name for p in pp_dir.glob("*.PDF")]
    )

    counts: List[int] = []
    in_window = 0
    for fname in all_pdfs:
        year = _parse_year_from_filename(fname)
        if year is None:
            continue
        if year < min_year or year > current_year:
            continue
        in_window += 1
        stem = str(fname).replace(".pdf", "").replace(".PDF", "").strip()
        n = _count_questions_for_pdf_stem(stem, base_dir)
        if n is not None and n > 0:
            counts.append(n)

    meta["papers_in_window"] = in_window
    meta["papers_with_blueprint"] = len(counts)
    meta["question_counts"] = counts

    if not counts:
        reason = "no_blueprints_in_window" if in_window else "no_pdfs_in_year_window"
        meta["fallback_reason"] = reason
        logger.info(
            "Paper A dynamic slots (mode): %s (window %s–%s, pdfs in window=%s) → fallback %s",
            reason,
            min_year,
            current_year,
            in_window,
            fallback,
        )
        return fallback, meta

    mode_val, mode_detail = _mode_question_count(counts)
    meta.update(mode_detail)

    num_slots = max(min_slots, min(max_slots, mode_val))
    meta["num_slots"] = num_slots
    meta["fallback_used"] = False
    meta["fallback_reason"] = None
    if num_slots != mode_val:
        meta["clamped_from_mode"] = mode_val

    logger.info(
        "Paper A dynamic slots (mode): mode=%s (freq=%s) over %s papers (years %s–%s) → num_slots=%s",
        mode_val,
        mode_detail["mode_frequency"],
        len(counts),
        min_year,
        current_year,
        num_slots,
    )
    return num_slots, meta
