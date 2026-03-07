import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import re

def extract_question_count_from_pdf(pdf_text):

    patterns = [
        r'Question\s+\d+',
        r'\d+[\.\)]\s+',
        r'^\s*\d+\.\s'
    ]
    count = 0
    lines = pdf_text.split('\n')
    
    for line in lines:
        line = line.strip()
        if any(re.search(pattern, line) for pattern in patterns):
            count += 1
    
    return max(1, count)

def analyze_question_distribution(lecture_data, question_files):
    results = []
    total_questions_all_lectures = 0
    
    question_counts = {}
    for q_file in question_files:
        try:
            # Extract text from question PDF
            from pdf_utils import extract_text_from_pdf
            q_text = extract_text_from_pdf(q_file)
            
            # Count questions in this file
            q_count = extract_question_count_from_pdf(q_text)
            question_counts[os.path.basename(q_file)] = q_count
            total_questions_all_lectures += q_count
        except Exception as e:
            print(f"Warning: Could not process {q_file}: {e}")
            question_counts[os.path.basename(q_file)] = 0
    
    print(f"\n   Total questions across all files: {total_questions_all_lectures}")
    
    # Now analyze each lecture
    for lecture in lecture_data:
        lecture_file = lecture['file']
        lecture_name = os.path.basename(lecture_file)
        lecture_title = lecture['title']
        
        # Find matching question file
        matching_question_file = lecture.get('question_file')
        
        if matching_question_file:
            q_filename = os.path.basename(matching_question_file)
            questions_in_lecture = question_counts.get(q_filename, 0)
            
            if total_questions_all_lectures > 0:
                percentage = (questions_in_lecture / total_questions_all_lectures) * 100
            else:
                percentage = 0
            
            results.append({
                'Lecture_File': lecture_name,
                'Lecture_Title': lecture_title,
                'Matching_Question_File': q_filename,
                'Questions_In_Lecture': questions_in_lecture,
                'Percentage_of_Total': round(percentage, 2),
                'Cumulative_Percentage': 0  # Will be calculated below
            })
        else:
            # No matching question file found
            results.append({
                'Lecture_File': lecture_name,
                'Lecture_Title': lecture_title,
                'Matching_Question_File': 'None',
                'Questions_In_Lecture': 0,
                'Percentage_of_Total': 0.0,
                'Cumulative_Percentage': 0
            })
    
    # Sort by percentage
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('Percentage_of_Total', ascending=False)
    
    # Calculate cumulative percentage
    results_df['Cumulative_Percentage'] = results_df['Percentage_of_Total'].cumsum()
    
    return results_df

def analyze_similarity_based_distribution(lecture_data, mcq_df, sims):
    if mcq_df.empty or sims.size == 0:
        return pd.DataFrame()
    
    lecture_question_counts = {}
    
    # Count questions by lecture
    for lecture in lecture_data:
        lecture_id = lecture['id']
        # Count questions explicitly assigned to this lecture
        lecture_questions = mcq_df[mcq_df['lecture_id'] == lecture_id]
        lecture_question_counts[lecture_id] = len(lecture_questions)
    
    # Calculate total
    total_questions = sum(lecture_question_counts.values())
    
    results = []
    for lecture in lecture_data:
        lecture_id = lecture['id']
        lecture_name = os.path.basename(lecture['file'])
        lecture_title = lecture['title']
        
        question_count = lecture_question_counts.get(lecture_id, 0)
        
        if total_questions > 0:
            percentage = (question_count / total_questions) * 100
        else:
            percentage = 0
        
        results.append({
            'Lecture_ID': lecture_id,
            'Lecture_File': lecture_name,
            'Lecture_Title': lecture_title,
            'Question_Count': question_count,
            'Percentage': round(percentage, 2)
        })
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('Percentage', ascending=False)
    results_df['Cumulative_Percentage'] = results_df['Percentage'].cumsum()
    
    return results_df

def generate_detailed_question_report(lecture_data, mcq_df):
    report_data = []
    
    for lecture in lecture_data:
        lecture_id = lecture['id']
        lecture_file = os.path.basename(lecture['file'])
        lecture_title = lecture['title']
        
        # Get questions for this lecture
        lecture_questions = mcq_df[mcq_df['lecture_id'] == lecture_id]
        
        if len(lecture_questions) > 0:
            # Get sample questions
            sample_questions = []
            for _, q in lecture_questions.head(3).iterrows():
                sample_questions.append(q['question'][:100] + "...")
        else:
            sample_questions = ["No questions found"]
        
        # Count by type (if available)
        question_types = {}
        if 'options' in mcq_df.columns:
            for _, q in lecture_questions.iterrows():
                options = str(q.get('options', ''))
                if 'A)' in options and 'B)' in options and 'C)' in options and 'D)' in options:
                    if 'MCQ' not in question_types:
                        question_types['MCQ'] = 0
                    question_types['MCQ'] += 1
                else:
                    if 'Descriptive' not in question_types:
                        question_types['Descriptive'] = 0
                    question_types['Descriptive'] += 1
        
        report_data.append({
            'Lecture': lecture_file,
            'Title': lecture_title,
            'Total_Questions': len(lecture_questions),
            'Question_Types': ', '.join([f"{k}:{v}" for k, v in question_types.items()]),
            'Sample_Questions': ' | '.join(sample_questions),
            'Topics_Covered': len(lecture.get('topics', [])),
            'Main_Topics': ', '.join([', '.join(t['keywords'][:2]) for t in lecture.get('topics', [])[:2]])
        })
    
    return pd.DataFrame(report_data)

def generate_study_plan_based_on_percentage(percentage_df, total_hours, study_days=None):
    if percentage_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    if study_days is None:
        study_days = max(1, total_hours // 2)
    
    # Create study plan
    study_plan = []
    
    for idx, row in percentage_df.iterrows():
        # Allocate hours based on percentage
        hours_allocated = (row['Percentage_of_Total'] / 100) * total_hours
        
        # Round to nearest 0.5 hours, minimum 0.5 hours
        hours_allocated = max(0.5, round(hours_allocated * 2) / 2)
        
        # Calculate priority based on percentage
        priority = idx + 1
        
        # Determine focus intensity
        if row['Percentage_of_Total'] > 20:
            intensity = "High"
        elif row['Percentage_of_Total'] > 10:
            intensity = "Medium"
        else:
            intensity = "Low"
        
        study_plan.append({
            'Priority': priority,
            'Lecture': row['Lecture_File'],
            'Title': row['Lecture_Title'][:50] + "..." if len(row['Lecture_Title']) > 50 else row['Lecture_Title'],
            'Question_Percentage': f"{row['Percentage_of_Total']}%",
            'Question_Count': row['Questions_In_Lecture'],
            'Recommended_Hours': hours_allocated,
            'Focus_Intensity': intensity,
            'Study_Focus': f"Focus on {row['Questions_In_Lecture']} key questions"
        })
    
    # Create daily schedule
    plan_df = pd.DataFrame(study_plan)
    daily_schedule = []
    
    remaining_hours = total_hours
    day_hours = total_hours / study_days
    current_day = 1
    
    while len(plan_df) > 0 and current_day <= study_days:
        day_lectures = []
        day_total_hours = 0
        
        # Try to fill this day with lectures
        for i in range(len(plan_df)):
            if i < len(plan_df):
                lecture = plan_df.iloc[i]
                if day_total_hours + lecture['Recommended_Hours'] <= day_hours:
                    day_lectures.append(lecture['Lecture'])
                    day_total_hours += lecture['Recommended_Hours']
                    plan_df = plan_df.drop(plan_df.index[i])
                    plan_df = plan_df.reset_index(drop=True)
                    i -= 1  # Adjust index after removal
        
        # Add to schedule
        if day_lectures:
            daily_schedule.append({
                'Day': current_day,
                'Date': (datetime.now() + timedelta(days=current_day-1)).strftime("%Y-%m-%d"),
                'Lectures': ', '.join(day_lectures),
                'Total_Hours': round(day_total_hours, 1),
                'Target': f"Complete {len(day_lectures)} lectures"
            })
        
        current_day += 1
    
    return pd.DataFrame(study_plan), pd.DataFrame(daily_schedule)

def create_percentage_summary_table(percentage_df):
    summary_table = []
    
    for _, row in percentage_df.iterrows():
        # Create visual representation
        bar_length = int(row['Percentage_of_Total'] / 2)
        bar = '█' * bar_length + '░' * (50 - bar_length)
        
        summary_table.append({
            'Lecture': row['Lecture_File'],
            'Questions': row['Questions_In_Lecture'],
            'Percentage': f"{row['Percentage_of_Total']:.1f}%",
            'Visual': bar,
            'Cumulative': f"{row['Cumulative_Percentage']:.1f}%"
        })
    
    return pd.DataFrame(summary_table)

def extract_questions_by_priority(lecture_data, percentage_df, num_priorities=4, questions_per_priority=7):
    """
    Extract questions from top priority lectures
    """
    top_priorities = percentage_df.head(num_priorities)
    
    all_extracted_questions = []
    
    for idx, row in top_priorities.iterrows():
        lecture_file = row['Lecture_File']
        lecture_info = next((lec for lec in lecture_data 
                             if os.path.basename(lec['file']) == lecture_file), None)
        
        if lecture_info and lecture_info.get('question_file'):
            from pdf_utils import extract_text_from_pdf
            from mcq_utils import extract_questions_from_pdf
            
            question_text = extract_text_from_pdf(lecture_info['question_file'])
            questions = extract_questions_from_pdf(question_text)
            
            # Take questions_per_priority questions or all if less
            num_to_take = min(questions_per_priority, len(questions))
            selected_questions = questions[:num_to_take]
            
            for q_idx, q in enumerate(selected_questions):
                all_extracted_questions.append({
                    'priority': idx + 1,
                    'lecture': lecture_file,
                    'lecture_title': lecture_info['title'],
                    'question_number': q_idx + 1,
                    'total_in_lecture': len(questions),
                    'question': q['text'],
                    'options': ' | '.join(q['options']) if q['options'] else ''
                })
    
    return pd.DataFrame(all_extracted_questions)

def generate_adaptive_study_plan(
    baseline_plan_df,
    progress_results,
    total_hours,
    study_days,
    alpha=0.5,
    max_increase=0.30,
    max_decrease=0.15
):
    """
    Generate adaptive study plan based on quiz progress results
    
    Parameters:
    - baseline_plan_df: DataFrame from baseline study plan
    - progress_results: Dictionary containing quiz results with lecture-wise accuracy
    - total_hours: Total study hours to allocate
    - study_days: Number of study days
    - alpha: Adaptation factor (0-1, higher = more aggressive adaptation)
    - max_increase: Maximum increase per lecture (e.g., 0.30 = 30%)
    - max_decrease: Maximum decrease per lecture (e.g., 0.15 = 15%)
    
    Returns:
    - adaptive_plan_df: Adaptive study plan DataFrame
    - adaptive_daily_df: Daily schedule DataFrame
    """
    if baseline_plan_df.empty:
        return pd.DataFrame(), pd.DataFrame()
    
    # Create copy of baseline plan
    adaptive_plan = []
    
    # Get lecture-wise accuracy from progress results
    lecture_accuracy = {}
    if 'lecture_wise_performance' in progress_results:
        for lecture_perf in progress_results['lecture_wise_performance']:
            lecture_accuracy[lecture_perf['lecture']] = lecture_perf['accuracy']
    elif 'accuracy_by_lecture' in progress_results:
        lecture_accuracy = progress_results['accuracy_by_lecture']
    else:
        # If no lecture-wise data, use overall accuracy for all lectures
        overall_accuracy = progress_results.get('overall_accuracy', 0.5)
        for _, row in baseline_plan_df.iterrows():
            lecture_accuracy[row['Lecture']] = overall_accuracy

    def _get_accuracy(lecture_name):
        """Resolve accuracy for lecture - try multiple key formats for robustness."""
        if lecture_name in lecture_accuracy:
            return lecture_accuracy[lecture_name]
        base = lecture_name.replace('.pdf', '') if lecture_name.endswith('.pdf') else lecture_name
        if base in lecture_accuracy:
            return lecture_accuracy[base]
        if f"{base}.pdf" in lecture_accuracy:
            return lecture_accuracy[f"{base}.pdf"]
        return 0.5
    
    # Calculate adaptive weights and hours
    adjusted_weights = []
    baseline_hours = []
    
    for idx, row in baseline_plan_df.iterrows():
        lecture = row['Lecture']
        baseline_hours_val = float(row['Recommended_Hours'])
        
        # Get accuracy for this lecture (default to 0.5 if not found)
        accuracy = _get_accuracy(lecture)
        
        # Calculate mastery gap (1 - accuracy)
        mastery_gap = 1 - accuracy
        
        # Calculate adjusted weight
        baseline_weight = float(row['Question_Percentage'].replace('%', '')) if isinstance(row['Question_Percentage'], str) else float(row['Question_Percentage'])
        adjusted_weight = baseline_weight * (1 + alpha * mastery_gap)
        
        adjusted_weights.append(adjusted_weight)
        baseline_hours.append(baseline_hours_val)
    
    # Normalize adjusted weights to match total hours
    total_adjusted_weight = sum(adjusted_weights)
    normalized_weights = [w / total_adjusted_weight * total_hours for w in adjusted_weights]
    
    # Apply guardrails and create adaptive plan
    adaptive_plan_data = []
    
    for idx, row in baseline_plan_df.iterrows():
        lecture = row['Lecture']
        baseline_hours_val = baseline_hours[idx]
        adjusted_hours = normalized_weights[idx]
        
        # Apply guardrails
        max_allowed_increase = baseline_hours_val * max_increase
        max_allowed_decrease = baseline_hours_val * max_decrease
        
        # Limit increase
        if adjusted_hours > baseline_hours_val + max_allowed_increase:
            adjusted_hours = baseline_hours_val + max_allowed_increase
        
        # Limit decrease
        if adjusted_hours < baseline_hours_val - max_allowed_decrease:
            adjusted_hours = baseline_hours_val - max_allowed_decrease
        
        # Minimum allocated time
        if adjusted_hours < 0.5:
            adjusted_hours = 0.5
        
        # Calculate delta
        delta_hours = adjusted_hours - baseline_hours_val
        
        # Determine focus intensity based on accuracy
        accuracy = _get_accuracy(lecture)
        if accuracy < 0.4:
            intensity = "High (Needs Focus)"
        elif accuracy < 0.7:
            intensity = "Medium (Review)"
        else:
            intensity = "Low (Maintain)"
        
        adaptive_plan_data.append({
            'Priority': row['Priority'],
            'Lecture': lecture,
            'Title': row['Title'],
            'Question_Percentage': row['Question_Percentage'],
            'Question_Count': row['Question_Count'],
            'Baseline_Hours': baseline_hours_val,
            'Adaptive_Hours': round(adjusted_hours * 2) / 2,  # Round to nearest 0.5
            'Delta_Hours': round(delta_hours * 2) / 2,
            'Quiz_Accuracy': f"{accuracy:.1%}",
            'Mastery_Gap': f"{mastery_gap:.1%}",
            'Focus_Intensity': intensity,
            'Study_Focus': f"Focus on {row['Question_Count']} key questions"
        })
    
    # Create adaptive plan DataFrame
    adaptive_plan_df = pd.DataFrame(adaptive_plan_data)
    
    # Create adaptive daily schedule (reuse existing logic)
    adaptive_daily_df = create_daily_schedule_from_plan(adaptive_plan_df, total_hours, study_days)
    
    return adaptive_plan_df, adaptive_daily_df

def create_daily_schedule_from_plan(plan_df, total_hours, study_days):
    """
    Create daily schedule from study plan (reused from baseline logic)
    """
    if plan_df.empty:
        return pd.DataFrame()
    
    daily_schedule = []
    remaining_plan = plan_df.copy()
    day_hours = total_hours / study_days
    current_day = 1
    
    while len(remaining_plan) > 0 and current_day <= study_days:
        day_lectures = []
        day_total_hours = 0
        
        # Try to fill this day with lectures
        for i in range(len(remaining_plan)):
            if i < len(remaining_plan):
                lecture = remaining_plan.iloc[i]
                adaptive_hours = lecture.get('Adaptive_Hours', lecture.get('Recommended_Hours', 0))
                
                if day_total_hours + adaptive_hours <= day_hours:
                    day_lectures.append(lecture['Lecture'])
                    day_total_hours += adaptive_hours
                    remaining_plan = remaining_plan.drop(remaining_plan.index[i])
                    remaining_plan = remaining_plan.reset_index(drop=True)
                    i -= 1  # Adjust index after removal
        
        # Add to schedule
        if day_lectures:
            daily_schedule.append({
                'Day': current_day,
                'Date': (datetime.now() + timedelta(days=current_day-1)).strftime("%Y-%m-%d"),
                'Lectures': ', '.join(day_lectures),
                'Total_Hours': round(day_total_hours, 1),
                'Target': f"Complete {len(day_lectures)} lectures"
            })
        
        current_day += 1
    
    return pd.DataFrame(daily_schedule)