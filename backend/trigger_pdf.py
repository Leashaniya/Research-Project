import json
import os
import sys
from pathlib import Path

# Add 'backend' to path for imports
sys.path.append(os.getcwd())

from app.services.pdf_service import PDFService

def run_pdf_export():
    # Use absolute paths based on script location for robustness
    SCRIPT_DIR = Path(__file__).resolve().parent
    DATA_DIR = SCRIPT_DIR.parent / "data"
    
    # Try both potential filenames
    paths_to_try = [
        DATA_DIR / "outputs" / "model_papers" / "agentic_model_paper.json",
        DATA_DIR / "outputs" / "model_papers" / "model_paper_latest.json"
    ]
    
    json_path = None
    for p in paths_to_try:
        if p.exists():
            json_path = p
            break
            
    if not json_path:
        print("❌ Error: Could not find any generated JSON in data/outputs/model_papers/")
        print("💡 Tip: Ensure you have generated the model paper first.")
        return

    pdf_path = json_path.with_suffix(".pdf")

    print(f"📄 Loading model paper from: {json_path}")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            paper_data = json.load(f)
        
        print(f"🎨 Exporting to PDF: {pdf_path}")
        PDFService.generate_pdf(paper_data, pdf_path)
        print("\n🏆 PDF GENERATION SUCCESSFUL!")
        print(f"📍 Location: {Path(os.getcwd()).resolve() / pdf_path}")
        
    except Exception as e:
        print(f"❌ PDF Export failed: {e}")

if __name__ == "__main__":
    run_pdf_export()
