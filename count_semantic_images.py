"""
Script to count how many images have been converted to semantic meaning
in the paper generation pipeline.
"""
import json
import sys
import os
from pathlib import Path
from collections import defaultdict

# Fix Windows console encoding
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUTS_DIR = DATA_DIR / "outputs"
TEXT_EXTRACTION_DIR = DATA_DIR / "text_extraction_hybrid"
SLIDES_EXTRACTION_DIR = DATA_DIR / "lecture_slides_extraction"

def count_past_paper_images():
    """Count images from past papers that were analyzed for semantic meaning"""
    print("\n" + "="*60)
    print("PAST PAPERS - Images Converted to Semantic Meaning")
    print("="*60)
    
    # Load diagrams manifest
    manifest_path = TEXT_EXTRACTION_DIR / "diagrams_manifest.json"
    if not manifest_path.exists():
        print(f"[ERROR] Diagrams manifest not found: {manifest_path}")
        return 0, {}
    
    manifest = json.loads(manifest_path.read_text())
    
    # Count by PDF
    by_pdf = defaultdict(int)
    total = len(manifest)
    
    for item in manifest:
        pdf_stem = item.get("pdf_stem", "Unknown")
        by_pdf[pdf_stem] += 1
    
    print(f"\n[OK] Total Images Analyzed: {total}")
    print(f"\n[STATS] Breakdown by PDF:")
    for pdf_stem, count in sorted(by_pdf.items()):
        print(f"   - {pdf_stem}: {count} images")
    
    return total, dict(by_pdf)

def count_lecture_slide_images():
    """Count images from lecture slides that were analyzed for semantic meaning"""
    print("\n" + "="*60)
    print("LECTURE SLIDES - Images Converted to Semantic Meaning")
    print("="*60)
    
    # Find all figures_metadata.jsonl files
    metadata_files = list(SLIDES_EXTRACTION_DIR.glob("*/figures_metadata.jsonl"))
    
    if not metadata_files:
        print(f"[ERROR] No figures metadata files found in: {SLIDES_EXTRACTION_DIR}")
        return 0, {}
    
    total = 0
    by_pdf = defaultdict(int)
    by_slide = defaultdict(int)
    
    for meta_file in metadata_files:
        pdf_stem = meta_file.parent.name
        slide_count = 0
        
        with open(meta_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("caption"):  # Only count if semantic analysis succeeded
                            slide_count += 1
                            slide_no = entry.get("slide_no", "?")
                            by_slide[f"{pdf_stem}_slide_{slide_no}"] += 1
                    except json.JSONDecodeError:
                        continue
        
        by_pdf[pdf_stem] = slide_count
        total += slide_count
    
    print(f"\n[OK] Total Images Analyzed: {total}")
    print(f"\n[STATS] Breakdown by PDF:")
    for pdf_stem, count in sorted(by_pdf.items()):
        print(f"   - {pdf_stem}: {count} images")
    
    return total, dict(by_pdf)

def count_generated_paper_images():
    """Count images/diagrams referenced in the generated paper"""
    print("\n" + "="*60)
    print("GENERATED PAPER - Diagram References")
    print("="*60)
    
    paper_path = OUTPUTS_DIR / "model_papers" / "agentic_model_paper.json"
    if not paper_path.exists():
        print(f"[ERROR] Generated paper not found: {paper_path}")
        return 0, {}
    
    paper = json.loads(paper_path.read_text())
    questions = paper.get("questions", [])
    
    diagram_count = 0
    diagram_details = []
    
    for q in questions:
        q_no = q.get("question_no", "?")
        
        # Check for diagram references
        if q.get("diagram_generated"):
            diagram_count += 1
            diagram_details.append({
                "question": q_no,
                "type": q.get("diagram_type", "Unknown"),
                "generated": True,
                "path": q.get("diagram_image_path", "N/A")
            })
        elif q.get("needs_diagram") or q.get("diagram_placeholder"):
            diagram_count += 1
            diagram_details.append({
                "question": q_no,
                "type": q.get("diagram_type", "Unknown"),
                "generated": False,
                "placeholder": True
            })
    
    print(f"\n[OK] Total Diagram References: {diagram_count}")
    print(f"\n[STATS] Breakdown by Question:")
    for detail in diagram_details:
        status = "[GENERATED]" if detail.get("generated") else "[PLACEHOLDER]"
        print(f"   - {detail['question']}: {detail['type']} - {status}")
    
    return diagram_count, diagram_details

def main():
    print("\n" + "="*60)
    print("IMAGE TO SEMANTIC MEANING CONVERSION REPORT")
    print("="*60)
    
    # Count past paper images
    past_paper_total, past_paper_by_pdf = count_past_paper_images()
    
    # Count lecture slide images
    slide_total, slide_by_pdf = count_lecture_slide_images()
    
    # Count generated paper diagrams
    paper_diagram_count, paper_details = count_generated_paper_images()
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\n[PAST PAPERS]")
    print(f"   - Total images analyzed: {past_paper_total}")
    print(f"   - PDFs processed: {len(past_paper_by_pdf)}")
    
    print(f"\n[LECTURE SLIDES]")
    print(f"   - Total images analyzed: {slide_total}")
    print(f"   - PDFs processed: {len(slide_by_pdf)}")
    
    print(f"\n[GENERATED PAPER]")
    print(f"   - Diagram references: {paper_diagram_count}")
    
    print(f"\n[GRAND TOTAL]")
    print(f"   - Source images converted to semantic meaning: {past_paper_total + slide_total}")
    print(f"   - Diagrams referenced in generated paper: {paper_diagram_count}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
