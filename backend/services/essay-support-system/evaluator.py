import openai
import json
from lecture_notes import extract_lecture_topics

openai.api_key = "add your api key here"


def extract_behaviour_metrics(result, user_answer):

    strengths = result["feedback"]["strengths"]

    # Ensure strengths is string
    if isinstance(strengths, list):
        strengths_text = ", ".join(strengths)
    else:
        strengths_text = strengths

    concept_count = len([x for x in strengths_text.split(",") if len(x.strip()) > 3])

    weaknesses = result["feedback"]["weaknesses"]

    # Ensure weaknesses is string
    if isinstance(weaknesses, list):
        weaknesses_text = ", ".join(weaknesses).lower()
    else:
        weaknesses_text = weaknesses.lower()

    mistakes = 0
    if "missing" in weaknesses_text:
        mistakes += 1
    if "incorrect" in weaknesses_text:
        mistakes += 1
    if "lack" in weaknesses_text:
        mistakes += 1

    answer_length = len(user_answer.split())

    return {
        "concept_count": concept_count,
        "mistakes": mistakes,
        "answer_length": answer_length
    }


def evaluate_and_feedback(user_answer, reference_answer, difficulty):
    lecture_topics = extract_lecture_topics()

    prompt = f"""
You are an expert university examiner.

Reference Answer:
{reference_answer}

Student Answer:
{user_answer}

Difficulty Level: {difficulty}

Lecture Topics:
{lecture_topics}

Return JSON ONLY with:
score, feedback(strengths, weaknesses, improvements),
study_recommendations, next_level
"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You evaluate answers like a strict examiner."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )

        content = response["choices"][0]["message"]["content"].strip()

        parsed = json.loads(content)

        behaviour = extract_behaviour_metrics(parsed, user_answer)
        parsed["behaviour"] = behaviour

        return parsed

    except Exception as e:
        print("OpenAI error:", e)

        return {
            "score": 50,
            "feedback": {
                "strengths": "Evaluation failed.",
                "weaknesses": "",
                "improvements": ""
            },
            "study_recommendations": [],
            "next_level": difficulty,
            "behaviour": {
                "concept_count": 0,
                "mistakes": 0,
                "answer_length": 0
            }
        }
