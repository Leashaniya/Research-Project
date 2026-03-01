import os
import random
import fitz
import pickle
import csv

from blooms import classify_bloom_level
from question_extractor import extract_questions
from evaluator import evaluate_and_feedback

DATA_DIR = "Data"
RL_FILE = "rl.pkl"
LOG_FILE = "attempt_log.csv"

ALPHA = 0.5
GAMMA = 0.9

# Load RL Policy
if os.path.exists(RL_FILE):
    with open(RL_FILE, "rb") as f:
        rl_policy = pickle.load(f)
else:
    rl_policy = {}

# ---------- READ QUESTIONS ----------
def read_pdfs():
    all_questions = []

    for root, _, files in os.walk(DATA_DIR):
        for f in files:
            if f.lower().endswith(".pdf"):
                pdf_path = os.path.join(root, f)
                doc = fitz.open(pdf_path)

                for page in doc:
                    text = page.get_text()
                    questions = extract_questions(text)

                    for q in questions:
                        level = classify_bloom_level(q)
                        topic = detect_topic(q)
                        all_questions.append({
                            "question": q,
                            "difficulty": level,
                            "topic": topic
                        })

    return all_questions


# ---------- TOPIC DETECTION ----------
def detect_topic(question):
    question_lower = question.lower()

    if "sql" in question_lower or "database" in question_lower:
        return "Database"
    elif "process" in question_lower or "cpu" in question_lower:
        return "OperatingSystems"
    elif "network" in question_lower or "protocol" in question_lower:
        return "Networks"
    else:
        return "General"


# ---------- UPDATE RL ----------
def update_policy(action_key, reward):

    old_value = rl_policy.get(action_key, 0.0)

    rl_policy[action_key] = old_value + ALPHA * (
        reward + GAMMA * max(rl_policy.values() or [0]) - old_value
    )

    with open(RL_FILE, "wb") as f:
        pickle.dump(rl_policy, f)


# ---------- LOG ATTEMPT ----------
def log_attempt(attempt_no, topic, difficulty, behaviour, reward):

    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode="a", newline="") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow(["attempt", "topic", "difficulty", "concepts", "mistakes", "reward"])

        writer.writerow([
            attempt_no,
            topic,
            difficulty,
            behaviour["concept_count"],
            behaviour["mistakes"],
            reward
        ])


# ---------- MAIN ----------
def main():

    print("\nLoading questions...")
    questions = read_pdfs()

    attempt_no = 1

    current_level = input("Select difficulty (easy / medium / hard): ").lower()
    if current_level not in ["easy", "medium", "hard"]:
        current_level = "easy"

    while True:

        # Filter questions by difficulty
        filtered = [q for q in questions if q["difficulty"] == current_level]

        if not filtered:
            print("No questions available for this level.")
            break

        selected = random.choice(filtered)

        print("\nQUESTION:")
        print(selected["question"])

        answer = input("\nYour Answer:\n")

        result = evaluate_and_feedback(answer, selected["question"], current_level)

        behaviour = result["behaviour"]

        # -------- Behaviour-Based Reward --------
        reward = 0

        if behaviour["concept_count"] >= 5:
            reward += 1

        if behaviour["mistakes"] >= 2:
            reward -= 1

        if behaviour["answer_length"] < 40:
            reward -= 0.5

        action_key = f"{current_level}_{selected['topic']}"

        update_policy(action_key, reward)

        log_attempt(attempt_no, selected["topic"], current_level, behaviour, reward)

        # Feedback display
        print("\nFeedback:")
        print("Strengths:", result["feedback"]["strengths"])
        print("Weaknesses:", result["feedback"]["weaknesses"])
        print("Improvements:", result["feedback"]["improvements"])

        print("\nReward:", reward)
        print("Policy Memory:", rl_policy)

        # Adaptive next difficulty
        if reward > 0 and current_level != "hard":
            current_level = "medium" if current_level == "easy" else "hard"
        elif reward < 0 and current_level != "easy":
            current_level = "medium" if current_level == "hard" else "easy"

        attempt_no += 1

        cont = input("\nContinue? (y/n): ").lower()
        if cont != "y":
            break


if __name__ == "__main__":
    main()