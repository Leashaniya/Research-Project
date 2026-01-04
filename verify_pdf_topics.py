
import sys
from pathlib import Path

# Add backend to path
backend_path = Path("backend").resolve()
sys.path.append(str(backend_path))

from app.services.pdf_service import PDFService

paper_data = {
    "total_marks": 100,
    "generated_at": "2026-04-01 12:00:00",
    "questions": [
        {
            "question_no": "1",
            "marks": 20,
            "main_topic": "SQL Database Schema and Queries",
            "subquestions": [
                {"label": "a", "text": "Define a primary key.", "marks": 5},
                {"label": "b", "text": "Write a SQL query to select all students.", "marks": 15}
            ]
        },
        {
            "question_no": "2",
            "marks": 25,
            "main_topic": "Normalization and Functional Dependencies",
            "subquestions": [
                {"label": "a", "text": "Explain 3NF.", "marks": 10},
                {"label": "b", "text": "Normalize the following table.", "marks": 15}
            ]
        }
    ]
}

output_path = "test_topic_headings.pdf"
PDFService.generate_pdf(paper_data, output_path)
print(f"Test PDF generated at: {output_path}")
