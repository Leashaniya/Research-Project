"""Extract priority questions for quiz - used by FastAPI quiz endpoint."""
import os
import re
import random
from typing import List, Dict, Any


def is_valid_mcq_question(question: dict) -> bool:
    """Check if a question has valid MCQ options (A/B/C/D format)."""
    if not question or not isinstance(question, dict):
        return False
    options = question.get("options", [])
    if not options or len(options) < 2:
        return False
    valid_option_count = sum(
        1 for opt in options if re.match(r"^[A-D][\.\)]", str(opt).strip())
    )
    return valid_option_count >= 2


def filter_valid_mcq_questions(questions: List[dict]) -> List[dict]:
    """Filter to only valid MCQ questions."""
    return [q for q in questions if is_valid_mcq_question(q)]


def extract_questions_from_top_priorities(
    lecture_data: List[Dict[str, Any]],
    percentage_df,
    num_priorities: int = 4,
    total_questions: int = 28,
) -> List[Dict[str, Any]]:
    """Extract questions from top priority lectures for the quiz."""
    if percentage_df.empty or not lecture_data:
        return []

    percentage_df = percentage_df.sort_values(
        "Percentage_of_Total", ascending=False
    ).reset_index(drop=True)
    top_priorities = percentage_df.head(num_priorities)

    extracted_questions = []

    for idx, row in top_priorities.iterrows():
        lecture_file = row["Lecture_File"]

        lecture_info = None
        for lecture in lecture_data:
            if os.path.basename(lecture["file"]) == lecture_file:
                lecture_info = lecture
                break

        if not lecture_info or not lecture_info.get("question_file"):
            continue

        question_file = lecture_info["question_file"]

        try:
            from pdf_utils import extract_text_from_pdf
            from mcq_utils import extract_questions_from_pdf

            question_text = extract_text_from_pdf(question_file)
            questions = extract_questions_from_pdf(
                question_text, use_openai_for_answers=False
            )

            valid_mcq_questions = filter_valid_mcq_questions(questions)
            questions_needed = 7
            selected_questions = []

            if len(valid_mcq_questions) >= questions_needed:
                selected_questions = random.sample(
                    valid_mcq_questions, questions_needed
                )
            else:
                selected_questions = valid_mcq_questions.copy()
                if len(selected_questions) < questions_needed:
                    remaining = [
                        q
                        for q in questions
                        if q not in valid_mcq_questions
                    ]
                    remaining.sort(
                        key=lambda x: len(x.get("options", [])),
                        reverse=True,
                    )
                    needed = questions_needed - len(selected_questions)
                    selected_questions.extend(remaining[:needed])

            random.shuffle(selected_questions)

            for i, q in enumerate(selected_questions):
                q_num = q.get("number", i + 1)
                extracted_questions.append({
                    "priority": idx + 1,
                    "lecture": lecture_file,
                    "lecture_title": lecture_info["title"],
                    "question_number": q_num,
                    "question_text": q["text"],
                    "options": " | ".join(q["options"]) if q.get("options") else "",
                    "answer": q.get("answer", ""),
                    "total_questions_in_lecture": len(questions),
                })

        except Exception as e:
            print(f"Error extracting questions from {question_file}: {e}")
            continue

    return extracted_questions
