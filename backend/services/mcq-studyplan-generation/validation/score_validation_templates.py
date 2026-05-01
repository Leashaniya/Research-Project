"""Score manually filled validation templates.

Expected inputs:
- outputs/topic_mapping_validation_template.csv
- outputs/recommendation_validation_template.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from topic_labels import clean_topic_display_name

OUTPUTS_DIR = BASE_DIR / "outputs"
TOPIC_TEMPLATE = OUTPUTS_DIR / "topic_mapping_validation_template.csv"
RECOMMENDATION_TEMPLATE = OUTPUTS_DIR / "recommendation_validation_template.csv"


def _safe_read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _topic_accuracy(df: pd.DataFrame, pred_col: str) -> float | None:
    if df.empty or "actual_topic" not in df.columns or pred_col not in df.columns:
        return None
    valid = df.dropna(subset=["actual_topic"])
    valid = valid[valid["actual_topic"].astype(str).str.strip() != ""]
    if valid.empty:
        return None
    hits = 0
    for _, row in valid.iterrows():
        actual = clean_topic_display_name(str(row["actual_topic"]))
        pred = clean_topic_display_name(str(row[pred_col]))
        if actual.lower() == pred.lower():
            hits += 1
    return round(hits / len(valid), 4)


def _precision_at_10(df: pd.DataFrame) -> float | None:
    if df.empty or "relevance_label" not in df.columns:
        return None
    top10 = df.head(10)
    if top10.empty:
        return None
    relevant = top10["relevance_label"].astype(str).str.strip().str.lower().eq("relevant").sum()
    return round(float(relevant) / 10.0, 4)


def main() -> None:
    topic_df = _safe_read(TOPIC_TEMPLATE)
    rec_df = _safe_read(RECOMMENDATION_TEMPLATE)

    keyword_acc = _topic_accuracy(topic_df, "keyword_predicted_topic")
    tfidf_acc = _topic_accuracy(topic_df, "tfidf_predicted_topic")
    embedding_acc = _topic_accuracy(topic_df, "embedding_predicted_topic")
    p10 = _precision_at_10(rec_df)

    print("[validation_scores] Topic mapping:")
    print(f" - keyword accuracy: {keyword_acc if keyword_acc is not None else 'manual labels missing'}")
    print(f" - tfidf accuracy: {tfidf_acc if tfidf_acc is not None else 'manual labels missing'}")
    print(f" - embedding accuracy: {embedding_acc if embedding_acc is not None else 'manual labels missing'}")
    print("[validation_scores] Recommendation:")
    print(f" - precision@10: {p10 if p10 is not None else 'manual relevance labels missing'}")


if __name__ == "__main__":
    main()

