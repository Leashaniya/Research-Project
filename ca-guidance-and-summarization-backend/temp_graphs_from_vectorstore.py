"""
Generate insight graphs directly from an existing LangChain FAISS vectorstore (index.pkl).
No backend code changes required.

Outputs PNG graphs into: graphs_from_vectorstore/

Graphs produced (meaningful + report-friendly):
1) Content composition (text/table/image) with consistent category colors
2) Top sources by stored doc count (horizontal bar)
3) Top sources by diagram count (horizontal bar)
4) Top sources by avg text chunk length (horizontal bar)
5) (Optional but strong) Stacked bar: Text vs Table vs Image per source (top N)
"""

import sys
import pickle
from pathlib import Path
from collections import Counter, defaultdict

import matplotlib.pyplot as plt


# -----------------------
# Helpers: project setup
# -----------------------
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT))


def find_latest_index_pkl(search_root: Path) -> Path:
    """Find the most recently modified index.pkl under search_root."""
    pkls = list(search_root.rglob("index.pkl"))
    if not pkls:
        raise FileNotFoundError(
            f"No index.pkl found under {search_root}. "
            "Locate the folder where you saved the FAISS store (contains index.faiss + index.pkl)."
        )
    pkls.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pkls[0]


def load_docstore(index_pkl_path: Path):
    """Load docstore from LangChain FAISS index.pkl."""
    with open(index_pkl_path, "rb") as f:
        data = pickle.load(f)

    # Common formats:
    # (docstore, index_to_docstore_id)  OR dict with keys
    if isinstance(data, tuple) and len(data) == 2:
        return data[0]
    if isinstance(data, dict) and "docstore" in data:
        return data["docstore"]

    raise ValueError(f"Unexpected format in {index_pkl_path} -> {type(data)}")


def get_all_docs(docstore):
    """Extract all Document objects from the docstore."""
    docs_dict = getattr(docstore, "_dict", None)
    if docs_dict is None:
        raise AttributeError(
            "docstore._dict not found. Your docstore format differs. "
            "Print type(docstore) and I’ll adjust the script."
        )
    return list(docs_dict.values())


def infer_doc_type(doc) -> str:
    """Infer type based on your conventions: [IMAGE:], [TABLE], metadata image_path."""
    content = (getattr(doc, "page_content", "") or "").strip()
    meta = getattr(doc, "metadata", {}) or {}

    if meta.get("image_path") or content.startswith("[IMAGE:"):
        return "image"
    if content.startswith("[TABLE]"):
        return "table"
    return "text"


def source_name(doc) -> str:
    """Use metadata['source'] if available; return filename only."""
    meta = getattr(doc, "metadata", {}) or {}
    src = meta.get("source") or "unknown"
    try:
        return Path(src).name
    except Exception:
        return str(src)


# -----------------------
# Plotting helpers
# -----------------------
COLOR_MAP = {
    "text": "#4C72B0",   # muted blue
    "table": "#55A868",  # muted green
    "image": "#C44E52",  # muted red
    "unknown": "#8172B2"
}


def plot_bar_category_colors(labels, values, title, xlabel, ylabel, out_path: Path):
    """Vertical bar with meaningful category colors (best for content composition)."""
    colors = [COLOR_MAP.get(l, COLOR_MAP["unknown"]) for l in labels]

    plt.figure()
    plt.bar(labels, values, color=colors)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()


def plot_barh(labels, values, title, xlabel, ylabel, out_path: Path, color=None):
    """Horizontal bar for long labels (best for lecture/source names)."""
    plt.figure()
    plt.barh(labels, values, color=color)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()


def plot_stacked_per_source(docs, out_path: Path, top_n: int = 10):
    """
    Stacked horizontal bar chart:
    For each top source, show count of text/table/image stored.
    """
    per_source = defaultdict(lambda: Counter())
    for d in docs:
        per_source[source_name(d)][infer_doc_type(d)] += 1

    totals = [(src, sum(c.values())) for src, c in per_source.items()]
    totals.sort(key=lambda x: x[1], reverse=True)

    top_sources = [src for src, _ in totals[:top_n]][::-1]  # reverse for readability (largest at top)

    text_vals = [per_source[s].get("text", 0) for s in top_sources]
    table_vals = [per_source[s].get("table", 0) for s in top_sources]
    image_vals = [per_source[s].get("image", 0) for s in top_sources]

    # Build left offsets for stacking
    left_table = text_vals
    left_image = [t + tb for t, tb in zip(text_vals, table_vals)]

    plt.figure()
    plt.barh(top_sources, text_vals, label="Text", color=COLOR_MAP["text"])
    plt.barh(top_sources, table_vals, left=left_table, label="Table", color=COLOR_MAP["table"])
    plt.barh(top_sources, image_vals, left=left_image, label="Image", color=COLOR_MAP["image"])

    plt.title(f"Top {top_n} Sources: Text vs Table vs Image (Stacked)")
    plt.xlabel("Count")
    plt.ylabel("Lecture / PDF")
    plt.legend()
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.show()


# -----------------------
# Main
# -----------------------
def main():
    # Search under app/ first (faster). If your vectorstore is elsewhere, change to PROJECT_ROOT.
    search_root = PROJECT_ROOT / "app"

    index_pkl = find_latest_index_pkl(search_root)
    print("✅ Using vectorstore:", index_pkl.parent)

    docstore = load_docstore(index_pkl)
    docs = get_all_docs(docstore)
    print(f"✅ Total docs in vectorstore: {len(docs)}")

    out_dir = PROJECT_ROOT / "graphs_from_vectorstore"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # Graph 1: Content composition (text/table/image) with colors
    # ---------------------------------------------------------
    type_counts = Counter(infer_doc_type(d) for d in docs)
    plot_bar_category_colors(
        labels=list(type_counts.keys()),
        values=list(type_counts.values()),
        title="Vectorstore Content Composition",
        xlabel="Content Type",
        ylabel="Count",
        out_path=out_dir / "01_content_composition.png",
    )

    # ---------------------------------------------------------
    # Graph 2: Docs per lecture/source (Top N) - horizontal bar
    # ---------------------------------------------------------
    docs_per_source = Counter(source_name(d) for d in docs)
    top_n = 12
    top_sources = docs_per_source.most_common(top_n)

    labels = [k for k, _ in top_sources][::-1]
    values = [v for _, v in top_sources][::-1]

    plot_barh(
        labels=labels,
        values=values,
        title=f"Top {top_n} Sources by Stored Document Count",
        xlabel="Doc Count",
        ylabel="Lecture / PDF",
        out_path=out_dir / "02_docs_per_source_top.png",
        color=COLOR_MAP["text"],
    )

    # ---------------------------------------------------------
    # Graph 3: Diagram count per lecture/source (Top N) - horizontal bar
    # ---------------------------------------------------------
    diagrams_per_source = Counter()
    for d in docs:
        if infer_doc_type(d) == "image":
            diagrams_per_source[source_name(d)] += 1

    if diagrams_per_source:
        top_diagrams = diagrams_per_source.most_common(top_n)
        labels = [k for k, _ in top_diagrams][::-1]
        values = [v for _, v in top_diagrams][::-1]

        plot_barh(
            labels=labels,
            values=values,
            title=f"Top {top_n} Sources by Diagram Count",
            xlabel="Diagram Count",
            ylabel="Lecture / PDF",
            out_path=out_dir / "03_diagrams_per_source_top.png",
            color=COLOR_MAP["table"],
        )
    else:
        print("⚠️ No image docs detected (no [IMAGE:] or image_path metadata). Skipping diagram graph.")

    # ---------------------------------------------------------
    # Graph 4: Avg text chunk length per source (Top N) - horizontal bar
    # ---------------------------------------------------------
    text_len_sum = defaultdict(int)
    text_len_count = defaultdict(int)

    for d in docs:
        if infer_doc_type(d) != "text":
            continue
        src = source_name(d)
        content = (getattr(d, "page_content", "") or "")
        text_len_sum[src] += len(content)
        text_len_count[src] += 1

    avg_len = {}
    for src in text_len_sum:
        avg_len[src] = text_len_sum[src] / max(text_len_count[src], 1)

    if avg_len:
        top_avg = sorted(avg_len.items(), key=lambda x: x[1], reverse=True)[:top_n]
        labels = [k for k, _ in top_avg][::-1]
        values = [v for _, v in top_avg][::-1]

        plot_barh(
            labels=labels,
            values=values,
            title=f"Top {top_n} Sources by Avg Text Chunk Length",
            xlabel="Avg Chunk Length (chars)",
            ylabel="Lecture / PDF",
            out_path=out_dir / "04_avg_chunk_length_top.png",
            color=COLOR_MAP["image"],
        )

    # ---------------------------------------------------------
    # Graph 5 (Optional): Stacked content distribution per source (Top N)
    # ---------------------------------------------------------
    plot_stacked_per_source(
        docs=docs,
        out_path=out_dir / "05_stacked_content_per_source.png",
        top_n=10,
    )

    print(f"\n✅ Saved graphs to: {out_dir}")


if __name__ == "__main__":
    main()
