# Service for slide extraction, chunking, embeddings, and FAISS

from backend.scripts.lectureslide_extract import main
import os

def process_lecture_slides(file_path):
    # Ensure the file exists
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Call the main function from the script
    main()

    return {
        "status": "success",
        "message": "Lecture slides processed successfully. Outputs generated."
    }