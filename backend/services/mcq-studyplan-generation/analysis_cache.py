"""
Persistent on-disk cache for Run Analysis: `data/{user_id}/` survives server restarts.

Artifacts:
  - mcq_data.json          — MCQ DataFrame (records)
  - lecture_chunks.pkl     — lecture_data, all_topics, percentage_df, detailed_report
  - embeddings.npy         — MCQ text embeddings (same as graph pipeline)
  - faiss_index.index      — topic×MCQ similarity matrix (.npy payload, not FAISS binary)
  - cache_manifest.json    — input signature + model/config version for invalidation
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

# Resolved by callers (mcq_service sets cwd to service root when run under FastAPI)
def _service_root() -> Path:
    return Path(__file__).resolve().parent


def sanitize_user_id(raw: str) -> str:
    s = (raw or "default").strip() or "default"
    s = re.sub(r"[^a-zA-Z0-9_\-]", "_", s)[:64]
    return s or "default"


def user_data_dir(user_id: str) -> Path:
    return _service_root() / "data" / sanitize_user_id(user_id)


def compute_input_signature() -> str:
    """
    Hash lecture + question PDF paths with mtime and size so edits invalidate the cache.
    Also folds in embedding model and topic-extraction limits (must match pipeline).
    """
    from pdf_utils import get_all_pdf_files
    from config import LECTURE_SLIDES_FOLDER, QUESTIONS_FOLDER
    from config import EMBED_MODEL_NAME, N_TOPICS, MAX_SENTENCES_PER_LECTURE

    parts: List[str] = [
        f"model:{EMBED_MODEL_NAME}",
        f"n_topics:{N_TOPICS}",
        f"max_sentences:{MAX_SENTENCES_PER_LECTURE}",
    ]
    for folder in (LECTURE_SLIDES_FOLDER, QUESTIONS_FOLDER):
        if not os.path.exists(folder):
            continue
        files = get_all_pdf_files(folder)
        for fpath in files:
            p = Path(fpath)
            if not p.is_file():
                continue
            st = p.stat()
            parts.append(f"{p.resolve()}:{st.st_mtime_ns}:{st.st_size}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _cache_file_names() -> Dict[str, str]:
    return {
        "mcq": "mcq_data.json",
        "chunks": "lecture_chunks.pkl",
        "embeddings": "embeddings.npy",
        "index": "faiss_index.index",
        "manifest": "cache_manifest.json",
    }


def dedupe_dataframe_columns(df: Optional[pd.DataFrame]) -> pd.DataFrame:
    """
    Keep the first of duplicate column names. Duplicates make iloc[] rows return
    multiple values per key (Series), which breaks graph code and can raise
    "truth value of a DataFrame/Series is ambiguous".
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    if not df.columns.duplicated(keep="first").any():
        return df
    return df.loc[:, ~df.columns.duplicated(keep="first")].copy()


def load_data(user_folder: Path, expected_signature: str) -> Optional[Dict[str, Any]]:
    """
    Load processed bundle if all artifacts exist and `cache_manifest.json` matches
    `expected_signature`. Otherwise returns None (caller runs full pipeline).
    """
    names = _cache_file_names()
    mcq_path = user_folder / names["mcq"]
    pkl_path = user_folder / names["chunks"]
    emb_path = user_folder / names["embeddings"]
    idx_path = user_folder / names["index"]
    man_path = user_folder / names["manifest"]

    if not all(p.exists() for p in (mcq_path, pkl_path, emb_path, idx_path, man_path)):
        return None

    try:
        manifest = json.loads(man_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if manifest.get("input_signature") != expected_signature:
        return None

    try:
        mcq_df = dedupe_dataframe_columns(pd.read_json(mcq_path, orient="records"))
        with open(pkl_path, "rb") as f:
            blob = pickle.load(f)
        mcq_embeddings = np.load(emb_path, allow_pickle=False)
        with open(idx_path, "rb") as f:
            sims = np.load(f, allow_pickle=False)
    except (OSError, ValueError, pickle.UnpicklingError):
        return None

    lecture_data = blob.get("lecture_data") or []
    all_topics = blob.get("all_topics") or []
    percentage_df = blob.get("percentage_df")
    detailed_report = blob.get("detailed_report")
    if percentage_df is None or not isinstance(percentage_df, pd.DataFrame):
        return None
    percentage_df = dedupe_dataframe_columns(percentage_df)
    if detailed_report is None:
        detailed_report = pd.DataFrame()
    elif not isinstance(detailed_report, pd.DataFrame):
        try:
            detailed_report = pd.DataFrame(detailed_report)
        except (TypeError, ValueError):
            detailed_report = pd.DataFrame()
    detailed_report = dedupe_dataframe_columns(detailed_report)

    return {
        "lecture_data": lecture_data,
        "all_topics": all_topics,
        "mcq_df": mcq_df,
        "percentage_df": percentage_df,
        "detailed_report": detailed_report,
        "sims": np.asarray(sims),
        "mcq_embeddings": np.asarray(mcq_embeddings),
        "manifest": manifest,
    }


def save_data(user_folder: Path, bundle: Dict[str, Any], input_signature: str) -> None:
    """Write all cache files under user_folder (mkdir as needed)."""
    names = _cache_file_names()
    user_folder.mkdir(parents=True, exist_ok=True)

    mcq_df: pd.DataFrame = dedupe_dataframe_columns(bundle["mcq_df"])
    percentage_df = dedupe_dataframe_columns(bundle["percentage_df"])
    detailed_report = bundle.get("detailed_report")
    if detailed_report is None:
        detailed_report = pd.DataFrame()
    else:
        detailed_report = dedupe_dataframe_columns(detailed_report)
    mcq_df.to_json(user_folder / names["mcq"], orient="records", indent=2)

    pkl_payload = {
        "lecture_data": bundle["lecture_data"],
        "all_topics": bundle["all_topics"],
        "percentage_df": percentage_df,
        "detailed_report": detailed_report,
    }
    with open(user_folder / names["chunks"], "wb") as f:
        pickle.dump(pkl_payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    emb = np.asarray(bundle["mcq_embeddings"])
    np.save(str(user_folder / "embeddings"), emb)

    sims = np.asarray(bundle["sims"])
    with open(user_folder / names["index"], "wb") as f:
        np.save(f, sims)

    from config import EMBED_MODEL_NAME, N_TOPICS, MAX_SENTENCES_PER_LECTURE

    manifest = {
        "input_signature": input_signature,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "embed_model": EMBED_MODEL_NAME,
        "n_topics": N_TOPICS,
        "max_sentences_per_lecture": MAX_SENTENCES_PER_LECTURE,
        "cache_version": 1,
    }
    (user_folder / names["manifest"]).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
