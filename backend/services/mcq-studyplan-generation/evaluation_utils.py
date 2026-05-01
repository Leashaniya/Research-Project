import json
import random
from datetime import datetime, timezone
from pathlib import Path

from topic_labels import clean_topic_display_name

def normalize_answer(answer):
    """Normalize answer to handle different formats (A, A., A), full text)"""
    if not answer:
        return ""
    
    answer = str(answer).strip().upper()
    
    # Extract single letter if it's at the start
    if len(answer) > 0 and answer[0] in 'ABCD':
        return answer[0]
    
    # Handle cases like "A." or "A)"
    if len(answer) > 1 and answer[0] in 'ABCD' and answer[1] in '.)':
        return answer[0]
    
    # If answer is already a single letter A, B, C, or D, return it
    if answer in 'ABCD':
        return answer
    
    return answer

def evaluate_answers(student_answers, correct_answers, question_meta=None):
    """Evaluate student answers against correct answers"""
    question_meta = question_meta or {}
    results = {
        'total_attempted': len(student_answers),
        'correct_count': 0,
        'wrong_count': 0,
        'accuracy': 0.0,
        'topic_wise': {},
        'topic_wise_accuracy': {},
        'weak_topics_confirmed': [],
        'detailed_results': []
    }

    topic_perf = {}
    
    for question_id, student_answer in student_answers.items():
        correct_answer = correct_answers.get(question_id, "")
        normalized_student = normalize_answer(student_answer)
        normalized_correct = normalize_answer(correct_answer)
        
        is_correct = normalized_student == normalized_correct
        
        if is_correct:
            results['correct_count'] += 1
        else:
            results['wrong_count'] += 1
        
        # Extract lecture info from question_id
        lecture = question_id.split('_')[0] if '_' in question_id else 'Unknown'
        meta = question_meta.get(question_id, {})
        topic_name = clean_topic_display_name((meta.get("topic_name") or "General").strip() or "General")
        
        if lecture not in results['topic_wise']:
            results['topic_wise'][lecture] = {'correct': 0, 'total': 0}
        
        results['topic_wise'][lecture]['total'] += 1
        if is_correct:
            results['topic_wise'][lecture]['correct'] += 1

        if topic_name not in topic_perf:
            topic_perf[topic_name] = {'correct': 0, 'total': 0}
        topic_perf[topic_name]['total'] += 1
        if is_correct:
            topic_perf[topic_name]['correct'] += 1
        
        results['detailed_results'].append({
            'question_id': question_id,
            'student_answer': student_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'lecture': lecture,
            'topic_name': topic_name,
        })
    
    # Calculate accuracy
    if results['total_attempted'] > 0:
        results['accuracy'] = (results['correct_count'] / results['total_attempted']) * 100
    
    # Calculate topic-wise accuracy
    for topic in results['topic_wise']:
        if results['topic_wise'][topic]['total'] > 0:
            results['topic_wise'][topic]['accuracy'] = (
                results['topic_wise'][topic]['correct'] / results['topic_wise'][topic]['total']
            ) * 100
        else:
            results['topic_wise'][topic]['accuracy'] = 0

    # Topic-wise accuracy with a small reliability safeguard
    # (<2 questions: keep band, but mark low evidence to avoid over-claiming)
    topic_rows = []
    for topic_name, perf in topic_perf.items():
        total = int(perf.get("total", 0))
        correct = int(perf.get("correct", 0))
        acc = (correct / total) * 100 if total > 0 else 0.0
        if acc < 50:
            band = "weak"
        elif acc <= 70:
            band = "moderate"
        else:
            band = "strong"
        reliable = total >= 2
        status = band if reliable else f"{band}_low_evidence"
        row = {
            "topic_name": topic_name,
            "correct": correct,
            "total": total,
            "accuracy": acc,
            "band": band,
            "status": status,
            "is_reliable": reliable,
        }
        results["topic_wise_accuracy"][topic_name] = row
        topic_rows.append(row)

    topic_rows.sort(key=lambda x: (x["accuracy"], -x["total"], x["topic_name"]))
    results["weak_topics_confirmed"] = [
        r["topic_name"] for r in topic_rows if r["band"] == "weak" and r["is_reliable"]
    ]

    _persist_graphrag_quiz_state(results)
    return results


def _persist_graphrag_quiz_state(results: dict) -> None:
    """Save last quiz summary for GraphRAG graph (rebuilt on next analysis). Best-effort; no crash on failure."""
    try:
        out = Path("outputs") / "graphrag_quiz_state.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "topic_wise": results.get("topic_wise", {}),
            "topic_wise_accuracy": results.get("topic_wise_accuracy", {}),
            "weak_topics_confirmed": results.get("weak_topics_confirmed", []),
            "overall_accuracy_pct": results.get("accuracy", 0.0),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(out, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError:
        pass

def prepare_quiz_questions(extracted_questions):
    """Prepare questions for quiz format with unique IDs, filtering for valid MCQ questions only"""
    quiz_questions = []
    
    # Group questions by priority to ensure we get exactly 7 per priority
    priority_groups = {}
    for q in extracted_questions:
        priority = q.get('priority', 0)
        if priority not in priority_groups:
            priority_groups[priority] = []
        priority_groups[priority].append(q)
    
    # Process each priority group (preserve extracted counts per group; no hard cap to 7)
    for priority in sorted(priority_groups.keys()):
        questions_in_priority = priority_groups[priority]
        valid_questions_in_priority = []
        
        # Filter for valid MCQ questions only
        for q in questions_in_priority:
            # Parse options if they're stored as a string
            options = q.get('options', '')
            if isinstance(options, str):
                options_list = [opt.strip() for opt in options.split(' | ') if opt.strip()]
            else:
                options_list = options if options else []
            
            # Validate that this question has proper MCQ options
            if is_valid_mcq_for_quiz(options_list):
                valid_questions_in_priority.append({
                    'question_id': f"{q.get('lecture', 'unknown').replace('.pdf', '')}_{q.get('question_number', 0)}",
                    'question_text': q.get('question_text', ''),
                    'options': options_list,
                    'correct_answer': q.get('answer', ''),
                    'lecture': q.get('lecture', ''),
                    'lecture_title': q.get('lecture_title', ''),
                    'priority': q.get('priority', 0),
                    'question_number': q.get('question_number', 0),
                    'topic_name': clean_topic_display_name(q.get('topic_name', 'General')),
                    'topic_confidence': q.get('topic_confidence', 0.0),
                    'topic_match_method': q.get('topic_match_method', 'fallback'),
                })
        
        # Keep all valid extracted questions for this priority.
        selected_questions = valid_questions_in_priority.copy()
        
        # Shuffle the selected questions for this priority
        random.shuffle(selected_questions)
        quiz_questions.extend(selected_questions)
        
        print(f"   Priority {priority}: Selected {len(selected_questions)} questions ({len(valid_questions_in_priority)} valid MCQs)")
    
    print(f"   Total quiz questions prepared: {len(quiz_questions)}")
    return quiz_questions

def is_valid_mcq_for_quiz(options_list):
    """Check if a question has valid MCQ options for the quiz"""
    if not options_list or len(options_list) < 2:
        return False
    
    # Check if options follow expected A/B/C/D format
    valid_option_count = 0
    for option in options_list:
        option = option.strip()
        if option and (option[0] in 'ABCD' and (len(option) == 1 or option[1] in '. )')):
            valid_option_count += 1
    
    # Require at least 2 valid MCQ options
    return valid_option_count >= 2
