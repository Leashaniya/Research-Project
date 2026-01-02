import json
import os
import sys
from pathlib import Path

# Add 'backend' to path for imports
sys.path.append(os.getcwd())

from app.services.pdf_service import PDFService

def run_pdf_export():
    # Paths (relative to backend directory)
    json_path = Path("../data/outputs/model_papers/agentic_model_paper.json")
    pdf_path = Path("../data/outputs/model_papers/agentic_model_paper.pdf")

    if not json_path.exists():
        print(f"❌ Error: Could not find generated JSON at {json_path}")
        print("💡 Tip: Ensure you have generated the model paper first.")
        return

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
