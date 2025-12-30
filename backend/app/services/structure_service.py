# Service for exam structure, topic clustering, and templates

from scripts.structure_topics_template import main

def generate_exam_structure():
    # Call the main function from the script
    main()

    return {
        "status": "success",
        "message": "Exam structure and topics generated successfully. Outputs saved."
    }