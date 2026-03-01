#!/usr/bin/env python3
"""Initialize the RAG system by building the vectorstore from lecture PDFs."""

import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set tokenizers parallelism to avoid warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Try to load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Download nltk data if needed
try:
    import nltk
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download("punkt", quiet=True)
except ImportError:
    pass

from app.ca_guidance.rag.config.settings import LECTURES_DIR
from app.ca_guidance.rag.ingestion.vectorstore_builder import ingest_lectures_folder

if __name__ == "__main__":
    print("Building vectorstore from lectures...")
    print(f"Lectures directory: {LECTURES_DIR}")
    
    if not LECTURES_DIR.exists():
        print(f"Error: Lectures directory does not exist: {LECTURES_DIR}")
        sys.exit(1)
    
    pdfs = list(LECTURES_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"Error: No PDF files found in {LECTURES_DIR}")
        sys.exit(1)
    
    print(f"Found {len(pdfs)} PDF file(s)")
    for pdf in pdfs:
        print(f"  - {pdf.name}")
    
    try:
        vs = ingest_lectures_folder(LECTURES_DIR, force_rebuild=True)
        if vs:
            print(f"\n✓ Vectorstore built successfully!")
            print(f"  Total vectors: {vs.index.ntotal}")
        else:
            print("\n✗ Failed to build vectorstore")
            sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error building vectorstore: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
