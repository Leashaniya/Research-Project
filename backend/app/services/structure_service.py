# # Service for exam structure, topic clustering, and templates

# from scripts.structure_topics_template import main

# def generate_exam_structure():
#     # Call the main function from the script
#     main()

#     return {
#         "status": "success",
#         "message": "Exam structure and topics generated successfully. Outputs saved."
#     }

from pathlib import Path
from scripts.structure_topics_template import main
from app.core.paths import ARTIFACTS_DIR

def ensure_structure_artifacts():
    req = [
        ARTIFACTS_DIR / "exam_blueprint_template.json",
        ARTIFACTS_DIR / "template_questions.json",
    ]
    if all(Path(p).exists() for p in req):
        return {"status": "ok", "message": "Artifacts already exist."}

    main()
    return {"status": "built", "message": "Artifacts created by structure_topics_template.py"}
