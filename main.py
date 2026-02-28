import os
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

import re
import json
import traceback
import random
from config import (
    LECTURE_SLIDES_FOLDER, QUESTIONS_FOLDER,
    OUTPUT_HTML, STUDY_PLAN_OUTPUT, SUMMARY_OUTPUT,
    N_TOPICS, MAX_SENTENCES_PER_LECTURE, OPENAI_API_KEY
)

from pdf_utils import (
    extract_text_from_pdf, get_all_pdf_files,
    extract_lecture_title, find_matching_question_file
)

from nlp_utils import extract_topics_from_text
from mcq_utils import (
    extract_questions_from_pdf, create_mcq_dataframe,
    compute_similarities
)
from analysis_utils import (
    analyze_question_distribution,
    analyze_similarity_based_distribution,
    generate_detailed_question_report,
    generate_study_plan_based_on_percentage,
    create_percentage_summary_table,
    extract_questions_by_priority
)
from graph_utils import build_pyvis_graph, llm_enrich_question

# Set OpenAI API key (keep for graph enrichment only)
import openai
openai.api_key = OPENAI_API_KEY


# ============= MAIN FUNCTIONS =============

def is_valid_mcq_question(question):
    """
    Check if a question has valid MCQ options
    Returns True only if the question has 4 valid options (A, B, C, D)
    """
    if not question or not isinstance(question, dict):
        return False
    
    options = question.get('options', [])
    
    # Check if options exist and have at least 2 choices (preferably 4)
    if not options or len(options) < 2:
        return False
    
    # Additional validation: check if options follow expected format
    valid_option_count = 0
    for option in options:
        # Check if option starts with A., B., C., or D. (or similar format)
        if re.match(r'^[A-D][\.\)]', option.strip()):
            valid_option_count += 1
    
    # Require at least 2 valid MCQ options (preferably 4)
    return valid_option_count >= 2

def filter_valid_mcq_questions(questions):
    """
    Filter out questions that don't have valid MCQ options
    Returns only questions with proper A/B/C/D options
    """
    valid_questions = []
    for question in questions:
        if is_valid_mcq_question(question):
            valid_questions.append(question)
        else:
            print(f"   ⚠ Filtering out question without valid options: {question.get('text', '')[:50]}...")
    
    print(f"   ✓ Filtered to {len(valid_questions)} valid MCQ questions from {len(questions)} total questions")
    return valid_questions

def extract_questions_from_top_priorities(lecture_data, percentage_df, num_priorities=4, total_questions=28):
    print("\n" + "=" * 80)
    print(" " * 20 + "EXTRACTING QUESTIONS FROM TOP PRIORITY LECTURES")
    print("=" * 80)
    
    # Sort by priority
    percentage_df = percentage_df.sort_values('Percentage_of_Total', ascending=False).reset_index(drop=True)
    top_priorities = percentage_df.head(num_priorities)
    
    extracted_questions = []
    all_questions_for_display = []
    
    for idx, row in top_priorities.iterrows():
        lecture_file = row['Lecture_File']
        
        # Find the lecture data for this file
        lecture_info = None
        for lecture in lecture_data:
            if os.path.basename(lecture['file']) == lecture_file:
                lecture_info = lecture
                break
        
        if lecture_info and 'question_file' in lecture_info and lecture_info['question_file']:
            question_file = lecture_info['question_file']
            
            # Extract questions from this file
            try:
                print(f"\n{'=' * 100}")
                print(f"Lecture Title: {lecture_info['title']}")
                print(f"{'=' * 100}\n")
                
                # Extract questions (without OpenAI answers)
                from pdf_utils import extract_text_from_pdf
                question_text = extract_text_from_pdf(question_file)
                questions = extract_questions_from_pdf(question_text, use_openai_for_answers=False)
                
                print(f"   Extracted {len(questions)} total questions from {lecture_file}")
                
                # Filter to only valid MCQ questions with proper A/B/C/D options
                valid_mcq_questions = filter_valid_mcq_questions(questions)
                
                # Try to get exactly 7 valid MCQ questions
                questions_needed = 7
                selected_questions = []
                
                if len(valid_mcq_questions) >= questions_needed:
                    # We have enough valid MCQ questions - randomly select 7
                    selected_questions = random.sample(valid_mcq_questions, questions_needed)
                    print(f"   ✓ Randomly selected {questions_needed} valid MCQ questions from {len(valid_mcq_questions)} available")
                else:
                    # Not enough valid MCQ questions - take all valid ones and try to supplement
                    selected_questions = valid_mcq_questions.copy()
                    print(f"   ⚠ Only {len(valid_mcq_questions)} valid MCQ questions found (need {questions_needed})")
                    
                    # Try to supplement with additional questions from the same lecture
                    # (even if they're not perfect MCQs, to ensure we have 7 questions total)
                    if len(selected_questions) < questions_needed:
                        additional_needed = questions_needed - len(selected_questions)
                        remaining_questions = [q for q in questions if q not in selected_questions]
                        
                        if remaining_questions:
                            # Take the best remaining questions (those with some options)
                            remaining_questions.sort(key=lambda x: len(x.get('options', [])), reverse=True)
                            additional_questions = remaining_questions[:additional_needed]
                            selected_questions.extend(additional_questions)
                            
                            print(f"   ⚠ Added {len(additional_questions)} additional questions to reach {questions_needed} total")
                
                # Shuffle the selected questions to ensure random ordering
                random.shuffle(selected_questions)
                
                print(f"Randomly selecting {len(selected_questions)} questions from {len(questions)} available questions:\n")
                print("-" * 100)
                
                # Display
                for i, q in enumerate(selected_questions):
                    q_num = q.get('number', i + 1)
                    
                    # Format and display question
                    formatted_q = format_question_for_display(q, idx + 1, lecture_file)
                    print(formatted_q)
                    
                    # Store for CSV
                    extracted_questions.append({
                        'priority': idx + 1,
                        'lecture': lecture_file,
                        'lecture_title': lecture_info['title'],
                        'question_number': q_num,
                        'question_text': q['text'],
                        'options': ' | '.join(q['options']) if q['options'] else '',
                        'answer': q.get('answer', ''),
                        'total_questions_in_lecture': len(questions)
                    })
                    
                    all_questions_for_display.append(formatted_q)
                    
            except Exception as e:
                print(f"Error extracting questions from {question_file}: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"\n⚠ No question file found for {lecture_file}\n")
    
    # Create a DataFrame
    if extracted_questions:
        questions_df = pd.DataFrame(extracted_questions)
        questions_df = questions_df.sort_values(['priority', 'question_number'])
        questions_df.to_csv("top_priority_questions.csv", index=False)
        save_formatted_questions(all_questions_for_display)
        print(f"\n   ✓ Extracted {len(extracted_questions)} questions from top priority lectures")
    
    return extracted_questions

def format_question_for_display(question, priority, lecture_file):
    q_num = question.get('number', 0)
    q_text = question.get('text', '').strip()
    options = question.get('options', [])
    answer = question.get('answer', '')
    
    # Format the question
    formatted = []
    
    formatted.append(f"{'─' * 100}")
    formatted.append(f"Question {q_num} (Priority {priority})")
    formatted.append(f"\n{q_text}")
    formatted.append("")
    
    # Add options
    if options:
        formatted.append("Options:")
        for option in options:
            formatted.append(f"  {option}")
    
    # Add answer if available
    if answer:
        formatted.append(f"\nAnswer: {answer}")
    
    formatted.append(f"{'─' * 100}")
    
    return "\n".join(formatted)

def save_formatted_questions(formatted_questions, filename="formatted_questions.txt"):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 100 + "\n")
            f.write(" " * 35 + "TOP PRIORITY QUESTIONS\n")
            f.write("=" * 100 + "\n\n")
            
            for question in formatted_questions:
                f.write(question + "\n\n")
        
        print(f"✓ Formatted questions saved to {filename}")
    except Exception as e:
        print(f"Error saving formatted questions: {e}")

def create_percentage_visualization(percentage_df, output_file="question_percentage_chart.png"):
    try:
        plt.figure(figsize=(12, 8))
        
        # Create subplot
        ax1 = plt.subplot(2, 1, 1)
        
        # Bar chart
        lectures = percentage_df['Lecture_File'].tolist()
        percentages = percentage_df['Percentage_of_Total'].tolist()
        
        # Set positions for bars
        x_pos = range(len(lectures))
        bars = ax1.bar(x_pos, percentages, color='skyblue', edgecolor='black')
        
        # Set x-axis ticks and labels
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(lectures, rotation=45, ha='right')
        
        # Add percentage labels on bars
        for bar, percentage in zip(bars, percentages):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2., height + 0.5,
                     f'{percentage:.1f}%', ha='center', va='bottom', fontsize=9)
        
        ax1.set_ylabel('Percentage of Total Questions (%)')
        ax1.set_title('Question Distribution Across Lectures')
        ax1.grid(True, alpha=0.3)
        
        # Cumulative percentage line chart
        ax2 = plt.subplot(2, 1, 2)
        cumulative_percentages = percentage_df['Cumulative_Percentage'].tolist()
        ax2.plot(x_pos, cumulative_percentages, 'o-', color='darkgreen', linewidth=2, markersize=8)
        ax2.fill_between(x_pos, 0, cumulative_percentages, alpha=0.2, color='green')
        
        # Set x-axis ticks and labels
        ax2.set_xticks(x_pos)
        ax2.set_xticklabels(lectures, rotation=45, ha='right')
        
        # Add labels to points
        for i, (lecture, cum_percent) in enumerate(zip(lectures, cumulative_percentages)):
            ax2.text(i, cum_percent + 2, f'{cum_percent:.1f}%',
                     ha='center', va='bottom', fontsize=9)
        
        ax2.set_ylabel('Cumulative Percentage (%)')
        ax2.set_xlabel('Lecture Files')
        ax2.set_title('Cumulative Question Coverage')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim([0, 110])
        
        plt.tight_layout()
        plt.savefig(output_file, dpi=150, bbox_inches='tight')
        plt.close()
        
        print(f"   ✓ Visualization saved to {output_file}")
        return True
    except Exception as e:
        print(f"   Could not create visualization: {e}")
        return False

def main():
    print("=" * 70)
    print("LECTURE QUESTION DISTRIBUTION ANALYSIS")
    print("=" * 70)
    
    # Get all PDF files
    print("\n Loading lecture slides and questions...")
    lecture_files = get_all_pdf_files(LECTURE_SLIDES_FOLDER)
    question_files = get_all_pdf_files(QUESTIONS_FOLDER)
    
    print(f"   Found {len(lecture_files)} lecture slides")
    print(f"   Found {len(question_files)} question files")
    
    if not lecture_files:
        print("Error: No lecture slides found!")
        return
    
    # Process lectures
    lecture_data = []
    all_mcq_data = []
    
    for i, lecture_file in enumerate(lecture_files):
        print(f"\n   Processing lecture {i + 1}/{len(lecture_files)}: {os.path.basename(lecture_file)}")
        
        # Extract lecture text
        lecture_text = extract_text_from_pdf(lecture_file)
        lecture_title = extract_lecture_title(lecture_text)
        
        # Extract topics from lecture
        topics = extract_topics_from_text(lecture_text, n_topics=N_TOPICS,
                                          max_sentences=MAX_SENTENCES_PER_LECTURE)
        
        matching_question_file = find_matching_question_file(lecture_file, question_files)
        
        questions = []
        if matching_question_file:
            print(f"   Matching questions: {os.path.basename(matching_question_file)}")
            question_text = extract_text_from_pdf(matching_question_file)
            # Extract questions without OpenAI answers
            questions = extract_questions_from_pdf(question_text, use_openai_for_answers=False)
            
            # Create MCQ dataframe for this lecture
            lecture_id = f"lec_{i + 1}"
            if questions:
                mcq_df = create_mcq_dataframe(questions, lecture_id)
                all_mcq_data.append(mcq_df)
                print(f"   Extracted {len(questions)} questions")
            
        else:
            print(f"   No matching question file found")
        
        # Store lecture data
        lecture_data.append({
            'id': f"lec_{i + 1}",
            'file': lecture_file,
            'title': lecture_title,
            'text': lecture_text[:1000] + "..." if len(lecture_text) > 1000 else lecture_text,
            'topics': topics,
            'question_file': matching_question_file,
            'question_count': len(questions)
        })
    
    # Combine all MCQ data
    if all_mcq_data:
        mcq_df = pd.concat(all_mcq_data, ignore_index=True)
        print(f"\n   Total questions extracted: {len(mcq_df)}")
    else:
        print("\n   No questions extracted from PDFs")
        mcq_df = pd.DataFrame(columns=['id', 'lecture_id', 'question', 'options', 'source'])
    
    # Combine all topics from all lectures
    all_topics = []
    topic_counter = 0
    for lecture in lecture_data:
        if 'topics' in lecture:
            for topic in lecture['topics']:
                # Give unique topic ID
                topic['topic_id'] = topic_counter
                topic['lecture_id'] = lecture['id']
                all_topics.append(topic)
                topic_counter += 1
    
    if all_topics and len(mcq_df) > 0:
        sims, mcq_embeddings = compute_similarities(all_topics, mcq_df)
        print(f"\n   Computed similarities between {len(all_topics)} topics and {len(mcq_df)} questions")
    else:
        sims = np.array([])
        mcq_embeddings = np.array([])
    
    # Analyze question distribution by percentage
    print("\n" + "=" * 70)
    print("QUESTION DISTRIBUTION ANALYSIS")
    print("=" * 70)
    
    percentage_df = analyze_question_distribution(lecture_data, question_files)
    
    if not percentage_df.empty:
        # Create summary table
        summary_table = create_percentage_summary_table(percentage_df)
        
        # Display table
        pd.set_option('display.max_colwidth', 30)
        print(summary_table.to_string(index=False))
        
        # Save detailed analysis
        percentage_df.to_csv("lecture_question_percentages.csv", index=False)
        print(f"\n   ✓ Saved lecture question percentages to lecture_question_percentages.csv")
        
        # Create visualization
        create_percentage_visualization(percentage_df)
    
    detailed_report = generate_detailed_question_report(lecture_data, mcq_df)
    
    # Generate study plan based on percentages
    print("\n" + "=" * 70)
    print("STUDY PLAN GENERATION")
    print("=" * 70)
    
    if not percentage_df.empty:
        # Get user input
        try:
            total_hours_input = input("\n   Total study hours available (default 20): ").strip()
            total_hours = float(total_hours_input) if total_hours_input else 20
            
            study_days_input = input("   Number of study days (default 10): ").strip()
            study_days = int(study_days_input) if study_days_input else 10
            
            print(f"\n   Using: {total_hours} hours over {study_days} days")
        except Exception as e:
            total_hours = 20
            study_days = 10
            print(f"   Using default: {total_hours} hours over {study_days} days")
        
        # Generate study plan
        study_plan_df, daily_schedule_df = generate_study_plan_based_on_percentage(
            percentage_df, total_hours, study_days
        )
        
        print("\n   RECOMMENDED STUDY PLAN :")
        print("   " + "-" * 80)
        
        # Display study plan
        for _, row in study_plan_df.iterrows():
            hours_str = f"{row['Recommended_Hours']:.1f}h".rjust(6)
            print(f"   Priority {row['Priority']:2}: {row['Lecture']:25} "
                  f"{row['Question_Percentage']:>8} → {hours_str} ({row['Focus_Intensity']})")
        
        # Save study plan
        study_plan_df.to_csv("percentage_based_study_plan.csv", index=False)
        daily_schedule_df.to_csv("daily_study_schedule.csv", index=False)
        
        print("\n   DAILY STUDY SCHEDULE:")
        print("   " + "-" * 60)
        for _, row in daily_schedule_df.iterrows():
            print(f"   Day {row['Day']}: {row['Date']} - {row['Lectures']}")
        
        print(f"\n   ✓ Saved study plan to percentage_based_study_plan.csv")
        print(f"   ✓ Saved daily schedule to daily_study_schedule.csv")
    
    # Build PyVis graph - only if it doesn't already exist
    if lecture_data and len(mcq_df) > 0:
        # Check if graph file already exists
        if os.path.exists(OUTPUT_HTML):
            print(f"\n   ✓ Graph file already exists: {OUTPUT_HTML}")
            print(f"   (Skipping creation - file already present)")
        else:
            try:
                print("\n" + "=" * 70)
                print("BUILDING INTERACTIVE GRAPH")
                print("=" * 70)
                build_pyvis_graph(lecture_data, mcq_df, sims, OUTPUT_HTML)
            except Exception as e:
                print(f"   Error building graph: {e}")
                traceback.print_exc()
    
    # Final summary
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE - SUMMARY")
    print("=" * 70)
    
    if not percentage_df.empty:
        # Create final summary table
        print("─" * 90)
        print(f"{'Lecture':<25} {'Questions':<10} {'Percentage':<12} {'Cumulative':<12} {'Priority'}")
        print("─" * 90)
        
        for idx, row in percentage_df.iterrows():
            # Determine priority icon
            if row['Percentage_of_Total'] > 20:
                priority = "★★★"
            elif row['Percentage_of_Total'] > 10:
                priority = "★★"
            else:
                priority = "★"
            
            print(f"{row['Lecture_File']:<25} {row['Questions_In_Lecture']:<10} "
                  f"{row['Percentage_of_Total']:<11.1f}% {row['Cumulative_Percentage']:<11.1f}% {priority}")
        
        print("─" * 90)
    
    if not detailed_report.empty:
        detailed_report.to_csv("detailed_question_report.csv", index=False)
        print(f"\n   ✓ Saved detailed question report to detailed_question_report.csv")
    
    # Extract questions from top priorities
    if not percentage_df.empty:
        extracted_questions = extract_questions_from_top_priorities(
            lecture_data, percentage_df, num_priorities=4, total_questions=28
        )
    
    # List output files
    print("\nOUTPUT FILES CREATED:")
    output_files = [
        "lecture_question_percentages.csv",
        "detailed_question_report.csv",
        "percentage_based_study_plan.csv",
        "daily_study_schedule.csv",
        "question_percentage_chart.png",
        OUTPUT_HTML,
        "top_priority_questions.csv",
        "formatted_questions.txt"
    ]
    
    files_found = 0
    for file in output_files:
        if os.path.exists(file):
            print(f"  ✓ {file}")
            files_found += 1
    
    if files_found == 0:
        print("  No output files found")
    
    print("\n" + "=" * 70)

def generate_study_plan_based_on_percentage(percentage_df, total_hours, study_days):
    df = percentage_df.copy()
    
    df["Recommended_Hours"] = (
            df["Percentage_of_Total"] / 100 * total_hours
    )
    
    df = df.sort_values("Recommended_Hours", ascending=False).reset_index(drop=True)
    df["Priority"] = df.index + 1
    
    df["Focus_Intensity"] = df["Percentage_of_Total"].apply(
        lambda x: "High" if x >= 20 else "Medium" if x >= 10 else "Low"
    )
    
    study_plan_df = df[[
        "Priority",
        "Lecture_File",
        "Percentage_of_Total",
        "Recommended_Hours",
        "Focus_Intensity"
    ]].rename(columns={
        "Lecture_File": "Lecture",
        "Percentage_of_Total": "Question_Percentage"
    })
    
    # Daily schedule
    start_date = datetime.today().date()
    daily_schedule = []
    
    for i, row in study_plan_df.iterrows():
        if i >= study_days:
            break
        
        daily_schedule.append({
            "Day": i + 1,
            "Date": (start_date + timedelta(days=i)).strftime("%Y-%m-%d"),
            "Lectures": row["Lecture"],
            "Total_Hours": round(row["Recommended_Hours"], 2)
        })
    
    daily_schedule_df = pd.DataFrame(daily_schedule)
    
    return study_plan_df, daily_schedule_df

if __name__ == "__main__":
    from datetime import timedelta
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nProgram interrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        traceback.print_exc()
    finally:
        print("\nProgram finished")