"""
Validate guidance image pipeline.

DEFAULT (recommended): generates a NEW ER PNG from a fixed sample scenario using the same
code path as production (generate_conceptual_er_dot + render_dot_to_png), checks that the
DOT mentions the expected entities/relationships, then runs extract_and_replace_images so
the figcaption matches the description that actually produced the image.

  cd backend/services/academic-guidance
  .venv\\Scripts\\python.exe scripts\\validate_guidance_image_pipeline.py

HTML-only (no OpenAI / no new PNG — reuses any existing guidance_er_diagram_*.png; caption
is explicitly NOT tied to that file's content):

  .venv\\Scripts\\python.exe scripts\\validate_guidance_image_pipeline.py --html-only

Legacy flag --try-er-tool is the same as default (generate); kept for backward compatibility.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GEN_DIR = ROOT / "app" / "ca_guidance" / "rag" / "generated_images"

# Single scenario: clear names so we can verify they appear in generated DOT.
SAMPLE_LIBRARY_ER_DESCRIPTION = (
    "Conceptual ER for one library scenario only.\n"
    "- Entity Book: primary key attribute ISBN; other attribute Title.\n"
    "- Entity Author: primary key attribute author_id; other attribute author_name.\n"
    "- Many-to-many relationship Writes between Book and Author (use cardinalities 0..* on both sides).\n"
    "Output must use these entity names (Book, Author) and relationship name Writes, and include ISBN."
)


def _pick_existing_er_png() -> str | None:
    if not GEN_DIR.is_dir():
        return None
    files = sorted(GEN_DIR.glob("guidance_er_diagram_*.png"))
    if not files:
        return None
    return files[-1].name


def _dot_covers_scenario(dot: str, description: str) -> tuple[bool, str]:
    """Lightweight check: DOT should mention the main nouns from our sample scenario."""
    low = dot.lower()
    # Anchors for SAMPLE_LIBRARY_ER_DESCRIPTION
    anchors = ["book", "author", "writes", "isbn"]
    found = [a for a in anchors if a in low]
    if len(found) < 3:
        return (
            False,
            f"DOT missing expected tokens from scenario (want most of {anchors}, found {found}). "
            "First 1200 chars of DOT:\n" + dot[:1200],
        )
    return True, ""


def generate_fresh_er_png(description: str) -> tuple[str | None, str]:
    """
    Same stack as diagram_image_tool ER branch: conceptual DOT from description, then PNG.
    Returns (basename, description) or (None, description) on failure.
    """
    from app.ca_guidance.tools.graphviz_er import generate_conceptual_er_dot, render_dot_to_png

    try:
        dot = generate_conceptual_er_dot(description)
    except Exception as e:
        print("FAIL: generate_conceptual_er_dot:", e)
        return None, description

    ok, msg = _dot_covers_scenario(dot, description)
    if not ok:
        print("FAIL: generated DOT does not match scenario (LLM drifted from description).")
        print(msg)
        return None, description

    try:
        png = render_dot_to_png(dot)
    except Exception as e:
        print("FAIL: render_dot_to_png:", e)
        return None, description

    GEN_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"guidance_er_diagram_{uuid.uuid4().hex[:10]}.png"
    out = GEN_DIR / fname
    out.write_bytes(png)
    print("OK: wrote fresh PNG:", out, "bytes:", len(png))
    return fname, description


def run_extract_checks(real_name: str, sample_description: str) -> int:
    from app.api.routes.protected import extract_and_replace_images
    from app.ca_guidance.tools.guidance_diagram_registry import (
        begin_guidance_diagram_registry,
        end_guidance_diagram_registry,
        get_guidance_diagram_registry,
        register_guidance_diagram_png,
    )

    begin_guidance_diagram_registry()
    try:
        register_guidance_diagram_png(real_name, sample_description)
        registry = get_guidance_diagram_registry()
        if not registry:
            print("FAIL: registry empty after register")
            return 1

        md = f"""### Image pipeline check

Markdown + HTML figure rendering.

[IMAGE:{real_name}]

#### Sketches (hallucinated - must remap to real PNGs)

![1:N](/api/images/1_N_relationship.png)

![placeholder](/api/images/filename.png)
"""
        html, paths = extract_and_replace_images(
            md,
            base_url="/api/images/",
            generate_explanations=False,
            diagram_registry=registry,
        )

        print("\n--- Resolved paths ---")
        for p in paths:
            print(" ", p)

        print("\n--- HTML ---\n", html, "\n--- checks ---", sep="")

        failures: list[str] = []
        if "<figure>" not in html:
            failures.append("missing <figure>")
        if "<figcaption" not in html:
            failures.append("missing <figcaption>")
        if real_name not in html:
            failures.append(f"missing real filename in HTML: {real_name}")
        if 'src="/api/images/1_N_relationship.png"' in html:
            failures.append("1_N_relationship.png still raw (remap failed)")
        if 'src="/api/images/filename.png"' in html:
            failures.append("filename.png still raw (remap failed)")
        cap_text = re.findall(r"<figcaption[^>]*>([^<]+)</figcaption>", html, re.I)
        if not cap_text:
            failures.append("no figcaption text captured")
        else:
            print("Figcaption(s):", cap_text[:5])

        if failures:
            for f in failures:
                print("FAIL:", f)
            return 1

        print("OK: figures, figcaptions, remapped hallucinated srcs")
        return 0
    finally:
        end_guidance_diagram_registry()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Do not call OpenAI: reuse any existing PNG; caption is a fixture (not image-specific).",
    )
    parser.add_argument(
        "--try-er-tool",
        action="store_true",
        help="(Deprecated) Same as default: generate a fresh ER PNG from the sample description.",
    )
    args = parser.parse_args()

    print("STEP 0: prepare PNG + description ...")

    if args.html_only:
        real = _pick_existing_er_png()
        if not real:
            print(
                "FAIL: No guidance_er_diagram_*.png under generated_images.\n"
                "  Run without --html-only once to generate a file, or run CA guidance."
            )
            return 1
        sample_desc = (
            "Automated HTML/remap test only: this PNG may be from an older run; "
            "figcaption does not describe this specific file's diagram content."
        )
        print("Mode: --html-only (no generation; arbitrary existing PNG)")
    else:
        # Default: fresh PNG from SAMPLE_LIBRARY_ER_DESCRIPTION (same stack as production).
        if args.try_er_tool:
            print("Note: --try-er-tool is redundant; default already generates ER.")
        print("Mode: generate fresh ER from built-in sample description (OpenAI required).")
        real, sample_desc = generate_fresh_er_png(SAMPLE_LIBRARY_ER_DESCRIPTION)
        if not real:
            print(
                "\nTip: run with --html-only to test HTML/remap only without OpenAI, "
                "or fix OPENAI_API_KEY / Graphviz / ER validation errors above."
            )
            return 1

    print("Using PNG:", GEN_DIR / real)
    print(
        "Registry / caption description (first 280 chars):",
        (sample_desc[:280] + "...") if len(sample_desc) > 280 else sample_desc,
    )

    print("Loading extract_and_replace_images (first import of app routes can take ~30-90s) ...")
    return run_extract_checks(real, sample_desc)


if __name__ == "__main__":
    raise SystemExit(main())
