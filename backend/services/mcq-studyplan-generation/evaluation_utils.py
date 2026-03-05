import random

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

def evaluate_answers(student_answers, correct_answers):
    """Evaluate student answers against correct answers"""
    results = {
        'total_attempted': len(student_answers),
        'correct_count': 0,
        'wrong_count': 0,
        'accuracy': 0.0,
        'topic_wise': {},
        'detailed_results': []
    }
    
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
        
        if lecture not in results['topic_wise']:
            results['topic_wise'][lecture] = {'correct': 0, 'total': 0}
        
        results['topic_wise'][lecture]['total'] += 1
        if is_correct:
            results['topic_wise'][lecture]['correct'] += 1
        
        results['detailed_results'].append({
            'question_id': question_id,
            'student_answer': student_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct,
            'lecture': lecture
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
    
    return results

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
    
    # Process each priority group
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
                    'question_number': q.get('question_number', 0)
                })
        
        # Ensure we have exactly 7 questions for this priority
        if len(valid_questions_in_priority) >= 7:
            # Randomly select 7 questions
            selected_questions = random.sample(valid_questions_in_priority, 7)
        else:
            # Take all valid questions and supplement if needed
            selected_questions = valid_questions_in_priority.copy()
            
            if len(selected_questions) < 7:
                # Try to supplement with remaining questions (even if not perfect MCQs)
                remaining_questions = [q for q in questions_in_priority if q not in valid_questions_in_priority]
                
                for q in remaining_questions:
                    if len(selected_questions) >= 7:
                        break
                    
                    # Parse options for remaining questions
                    options = q.get('options', '')
                    if isinstance(options, str):
                        options_list = [opt.strip() for opt in options.split(' | ') if opt.strip()]
                    else:
                        options_list = options if options else []
                    
                    # Add the question even if it's not a perfect MCQ
                    selected_questions.append({
                        'question_id': f"{q.get('lecture', 'unknown').replace('.pdf', '')}_{q.get('question_number', 0)}",
                        'question_text': q.get('question_text', ''),
                        'options': options_list,
                        'correct_answer': q.get('answer', ''),
                        'lecture': q.get('lecture', ''),
                        'lecture_title': q.get('lecture_title', ''),
                        'priority': q.get('priority', 0),
                        'question_number': q.get('question_number', 0)
                    })
        
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
