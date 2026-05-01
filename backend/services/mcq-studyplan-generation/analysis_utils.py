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
            'Percentage_of_Total': float(row['Percentage_of_Total']),
            'Question_Percentage': f"{row['Percentage_of_Total']}%",
            'Question_Count': row['Questions_In_Lecture'],
            'Recommended_Hours': hours_allocated,
            'Focus_Intensity': intensity,
            'Study_Focus': f"Focus on {row['Questions_In_Lecture']} key questions"
        })
    
    # Create daily schedule with strict priority order (split lectures across days).
    plan_df = pd.DataFrame(study_plan)
    sorted_lectures = plan_df.sort_values("Percentage_of_Total", ascending=False).reset_index(drop=True)
    print(f"[schedule_debug] sorted order: {sorted_lectures['Percentage_of_Total'].tolist()}")
    print(f"[schedule_debug] lecture order: {sorted_lectures['Lecture'].tolist()}")
    day_hours = float(total_hours) / float(study_days) if study_days else float(total_hours)
    day_hours = max(0.5, day_hours)
    tolerance = 0.1

    def _to_topic_list(value):
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            return parts
        return []

    def _hours_display(hours_value: float) -> str:
        total_minutes = max(0, int(round(float(hours_value) * 60)))
        h = total_minutes // 60
        m = total_minutes % 60
        if h and m:
            return f"{h} hour{'s' if h != 1 else ''} {m} minutes"
        if h:
            return f"{h} hour{'s' if h != 1 else ''}"
        return f"{m} minutes"

    daily_schedule = []
    day_number = 1
    remaining_in_day = day_hours
    current_day_items = []
    current_day_hours = 0.0
    base_date = datetime.today()
    lecture_parts_by_name = {}

    lecture_states = []
    for _, lecture in sorted_lectures.iterrows():
        lecture_states.append(
            {
                "lecture": str(lecture.get("Lecture", "")).strip(),
                "topics": _to_topic_list(lecture.get("Title", "")),
                "remaining": float(lecture.get("Recommended_Hours", 0.0) or 0.0),
            }
        )

    lec_idx = 0
    while day_number <= study_days and lec_idx < len(lecture_states):
        current_day_items = []
        current_day_hours = 0.0
        # Cap to requested days; last day absorbs all remaining lecture chunks.
        remaining_in_day = float("inf") if day_number == study_days else day_hours

        while lec_idx < len(lecture_states):
            state = lecture_states[lec_idx]
            if state["remaining"] <= tolerance:
                lec_idx += 1
                continue

            fit_hours = min(state["remaining"], remaining_in_day)
            current_day_items.append(
                {
                    "lecture": state["lecture"],
                    "hours": round(float(fit_hours), 2),
                    "topics": state.get("topics", []),
                }
            )
            state["remaining"] -= float(fit_hours)
            current_day_hours += float(fit_hours)
            remaining_in_day -= float(fit_hours)

            if remaining_in_day <= tolerance:
                break
            if day_number != study_days and state["remaining"] > tolerance:
                break
            if state["remaining"] <= tolerance:
                lec_idx += 1

        if not current_day_items:
            break

        focus_topics = []
        seen_topics = set()
        for item in current_day_items:
            for t in item.get("topics", []):
                tn = str(t).strip()
                if tn and tn not in seen_topics:
                    seen_topics.add(tn)
                    focus_topics.append(tn)

        lecture_names = [item["lecture"] for item in current_day_items if item.get("lecture")]
        primary_lecture = lecture_names[0] if lecture_names else ""
        part_num = lecture_parts_by_name.get(primary_lecture, 0) + 1
        lecture_parts_by_name[primary_lecture] = part_num
        lecture_display = primary_lecture if part_num == 1 else f"{primary_lecture} (Part {part_num})"

        day_total = round(float(current_day_hours), 2)
        daily_schedule.append(
            {
                # Existing fields kept for current frontend/API compatibility.
                "Day": day_number,
                "Date": (base_date + timedelta(days=day_number - 1)).strftime("%Y-%m-%d"),
                "Lectures": lecture_display,
                "Total_Hours": round(day_total, 1),
                "Target": f"Complete {len(lecture_names)} lecture segment(s)",
                # New explicit schedule fields.
                "day": day_number,
                "date": (base_date + timedelta(days=day_number - 1)).strftime("%Y-%m-%d"),
                "lecture": lecture_display,
                "focus_topics": focus_topics,
                "suggested_hours": day_total,
                "hours_display": _hours_display(day_total),
                "task": "Practice 5 questions + revise notes",
            }
        )
        print(f"[schedule_debug] Day {day_number}: {lecture_display} ({day_total}hrs)")
        day_number += 1

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


def bkt_update_sequence(sequence):
    """
    Lightweight BKT update over a correctness sequence.
    sequence: iterable of 0/1 or bool values.
    returns: mastery probability in [0, 1]
    """
    p_known = 0.30
    p_guess = 0.25
    p_slip = 0.10
    p_learn = 0.10

    if not sequence:
        return float(p_known)

    try:
        for obs in sequence:
            correct = bool(obs)
            if correct:
                num = p_known * (1.0 - p_slip)
                den = num + (1.0 - p_known) * p_guess
            else:
                num = p_known * p_slip
                den = num + (1.0 - p_known) * (1.0 - p_guess)

            if den <= 0:
                posterior = p_known
            else:
                posterior = num / den

            # Learning transition after this observation.
            p_known = posterior + (1.0 - posterior) * p_learn
            p_known = max(0.0, min(1.0, p_known))
    except Exception:
        return 0.30

    return float(p_known)


def normalize_lecture_name(name):
    if not name:
        return ""
    return str(name).replace(".pdf", "").strip().lower()


def build_sequences(progress_results):
    """
    Build lecture-wise correctness sequences from progress_results["detailed_results"].
    Returns dict: {lecture_name: [0, 1, ...]}
    """
    sequences = {}
    try:
        details = (progress_results or {}).get("detailed_results", []) or []
        if not isinstance(details, list):
            return {}

        for item in details:
            if not isinstance(item, dict):
                continue
            lecture = normalize_lecture_name(item.get("lecture", ""))
            if not lecture:
                continue
            val = item.get("is_correct", False)
            correctness = 1 if bool(val) else 0
            sequences.setdefault(lecture, []).append(correctness)
    except Exception:
        return {}

    return sequences


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

    progress_results = progress_results if isinstance(progress_results, dict) else {}
    print(" BKT DEBUG START")
    print("progress_results keys:", list(progress_results.keys()))
    print("detailed_results exists:", "detailed_results" in progress_results)
    if "detailed_results" not in progress_results:
        print("[BKT] No detailed_results found -> fallback mode active")
    
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

    # Add normalized lecture-name aliases for robust lookup.
    lecture_accuracy_norm = {}
    for k, v in lecture_accuracy.items():
        nk = normalize_lecture_name(k)
        if nk:
            lecture_accuracy_norm[nk] = v
    if lecture_accuracy_norm:
        lecture_accuracy.update(lecture_accuracy_norm)

    def _get_accuracy(lecture_name):
        """Resolve accuracy for lecture - try multiple key formats for robustness."""
        lecture_norm = normalize_lecture_name(lecture_name)
        if lecture_name in lecture_accuracy:
            val = lecture_accuracy[lecture_name]
            val = float(val)
            return (val / 100.0) if val > 1 else val
        if lecture_norm in lecture_accuracy:
            val = float(lecture_accuracy[lecture_norm])
            return (val / 100.0) if val > 1 else val
        base = lecture_name.replace('.pdf', '') if lecture_name.endswith('.pdf') else lecture_name
        if base in lecture_accuracy:
            val = float(lecture_accuracy[base])
            return (val / 100.0) if val > 1 else val
        if f"{base}.pdf" in lecture_accuracy:
            val = float(lecture_accuracy[f"{base}.pdf"])
            return (val / 100.0) if val > 1 else val
        if normalize_lecture_name(base) in lecture_accuracy:
            val = float(lecture_accuracy[normalize_lecture_name(base)])
            return (val / 100.0) if val > 1 else val
        return 0.5

    print("[BKT] Building sequences...")
    sequence_map = build_sequences(progress_results)
    print("[BKT] Sequence map size:", len(sequence_map))
    
    # Calculate adaptive weights and hours
    adjusted_weights = []
    baseline_hours = []
    
    mastery_meta = {}
    for idx, row in baseline_plan_df.iterrows():
        lecture = row['Lecture']
        baseline_hours_val = float(row['Recommended_Hours'])
        
        # Get accuracy for this lecture (default to 0.5 if not found)
        accuracy = _get_accuracy(lecture)
        sequence = sequence_map.get(normalize_lecture_name(lecture), [])
        print("[BKT VALIDATION] Lecture:", lecture)
        print("[BKT VALIDATION] Sequence:", sequence)
        print("[BKT VALIDATION] Accuracy:", accuracy)
        print(f"[BKT TRACE] lecture={lecture} sequence_len={len(sequence)}")
        bkt_mastery = None
        final_mastery = accuracy
        try:
            if not isinstance(sequence, list):
                print("[BKT SKIPPED] sequence is not a list")
                sequence = []

            if len(sequence) < 3:
                print("[BKT SKIPPED] insufficient sequence length")
            elif len(sequence) >= 3:
                bkt_mastery = bkt_update_sequence(sequence)
                final_mastery = (0.7 * accuracy) + (0.3 * bkt_mastery)
                print(f"[BKT ACTIVE] {lecture} bkt={bkt_mastery:.3f}")
        except Exception:
            bkt_mastery = None
            final_mastery = accuracy
            print(f"[BKT SKIPPED] {lecture} fallback due to error")

        final_mastery = max(0.0, min(1.0, float(final_mastery)))
        print("[BKT OUTPUT] BKT Mastery:", bkt_mastery)
        print("[BKT OUTPUT] Final Mastery:", final_mastery)
        if abs(final_mastery - accuracy) < 0.01:
            print("[WARNING] BKT has no effect -> check sequence or model")
        else:
            print("[OK] BKT is influencing mastery values")

        # Calculate mastery gap (1 - final_mastery)
        mastery_gap = 1 - final_mastery

        print(
            f"[BKT Adaptive] lecture={lecture} accuracy={accuracy:.2f} "
            f"bkt={bkt_mastery if bkt_mastery is not None else 'N/A'} "
            f"final={final_mastery:.2f} questions={len(sequence)}"
        )
        
        # Calculate adjusted weight
        baseline_weight = float(row['Question_Percentage'].replace('%', '')) if isinstance(row['Question_Percentage'], str) else float(row['Question_Percentage'])
        adjusted_weight = baseline_weight * (1 + alpha * mastery_gap)
        
        adjusted_weights.append(adjusted_weight)
        baseline_hours.append(baseline_hours_val)
        mastery_meta[lecture] = {
            "accuracy": accuracy,
            "bkt_mastery": bkt_mastery,
            "final_mastery": final_mastery,
            "mastery_gap": mastery_gap,
            "questions": len(sequence),
        }
    
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
        meta = mastery_meta.get(lecture, {})
        bkt_mastery = meta.get("bkt_mastery", None)
        final_mastery = float(meta.get("final_mastery", accuracy))
        mastery_gap = float(meta.get("mastery_gap", 1 - accuracy))
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
            'BKT_Mastery': round(float(bkt_mastery), 4) if bkt_mastery is not None else "N/A",
            'Final_Mastery': round(final_mastery, 4),
            'Mastery_Gap': f"{mastery_gap:.1%}",
            'Focus_Intensity': intensity,
            'Study_Focus': f"Focus on {row['Question_Count']} key questions"
        })

    total_lectures = len(mastery_meta)
    bkt_active_count = sum(1 for m in mastery_meta.values() if m.get("bkt_mastery") is not None)
    skipped_count = max(0, total_lectures - bkt_active_count)
    print(" BKT FINAL STATUS SUMMARY")
    print("Lectures processed:", len(sequence_map))
    print("BKT active lectures:", bkt_active_count)
    print("Fallback lectures:", skipped_count)
    print("\n===== BKT SUMMARY =====")
    print("Total lectures:", total_lectures)
    print("BKT active lectures:", bkt_active_count)
    print("BKT skipped lectures:", skipped_count)
    
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


# --- GraphRAG: quiz strength + priority (exam-frequency proxy) helpers ---

GRAPH_RAG_WEAK_ACCURACY_BELOW = 60.0
GRAPH_RAG_STRONG_ACCURACY_FROM = 75.0


def classify_quiz_accuracy_band(
    accuracy_pct,
    weak_below: float = GRAPH_RAG_WEAK_ACCURACY_BELOW,
    strong_from: float = GRAPH_RAG_STRONG_ACCURACY_FROM,
):
    """
    Map quiz accuracy (0–100 scale) to a simple band for graph styling and retrieval.
    Returns: 'weak' | 'strong' | 'neutral' | 'unknown'
    """
    if accuracy_pct is None:
        return "unknown"
    try:
        a = float(accuracy_pct)
    except (TypeError, ValueError):
        return "unknown"
    if a < weak_below:
        return "weak"
    if a >= strong_from:
        return "strong"
    return "neutral"


def lecture_mcq_share_dataframe(lecture_data, mcq_df: pd.DataFrame, sims: np.ndarray) -> pd.DataFrame:
    """
    Per-lecture share of dataset MCQs (proxy for how often the topic appears in exams).
    Same semantics as analyze_similarity_based_distribution with a count-based fallback.
    """
    dist = analyze_similarity_based_distribution(lecture_data, mcq_df, sims)
    if not dist.empty:
        return dist.sort_values("Percentage", ascending=False).reset_index(drop=True)
    counts = {}
    for _, row in mcq_df.iterrows():
        lid = row.get("lecture_id")
        for lec in lecture_data:
            if lec["id"] == lid:
                fn = os.path.basename(lec["file"])
                counts[fn] = counts.get(fn, 0) + 1
                break
    total = sum(counts.values()) or 1
    rows = [
        {
            "Lecture_File": fn,
            "Percentage": round(100.0 * c / total, 2),
            "Question_Count": c,
        }
        for fn, c in counts.items()
    ]
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("Percentage", ascending=False).reset_index(drop=True)