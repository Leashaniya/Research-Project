import json
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.pdf_service import PDFService

def rebuild():
    json_path = "data/outputs/model_papers/agentic_model_paper.json"
    pdf_path = "data/outputs/model_papers/agentic_model_paper.pdf"
    
    if not os.path.exists(json_path):
        print(f"File not found: {json_path}")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        paper_data = json.load(f)
    
    print(f"Rebuilding PDF from {json_path}...")
    PDFService.generate_pdf(paper_data, pdf_path)
    print(f"Success! PDF rebuilt at {pdf_path}")

if __name__ == "__main__":
    rebuild()
