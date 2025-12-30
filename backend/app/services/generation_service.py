# Service for OpenAI-based RAG model paper generation

from backend.scripts.generate_model_paper_openai import main

def generate_model_paper():
    # Call the main function from the script
    main()

    return {
        "status": "success",
        "output_json": "data/outputs/model_papers/model_paper_latest.json",
        "output_txt": "data/outputs/model_papers/model_paper_latest.txt"
    }