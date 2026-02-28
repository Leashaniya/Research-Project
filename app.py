import os
import sys
import pandas as pd
import numpy as np
import json
import plotly
import plotly.express as px
import plotly.graph_objects as go
from flask import Flask, render_template, request, jsonify, send_file, url_for, flash, session, redirect
from datetime import datetime, timedelta
import traceback
import io
import base64
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import main as lecture_analysis
import random
from evaluation_utils import evaluate_answers, prepare_quiz_questions

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['OUTPUT_FOLDER'] = 'outputs'

# Create necessary folders
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Global variables
app.config['LECTURE_DATA'] = []
app.config['MCQ_DF'] = pd.DataFrame()
app.config['PERCENTAGE_DF'] = pd.DataFrame()
app.config['ALL_TOPICS'] = []
app.config['STUDY_PLAN_DF'] = pd.DataFrame()
app.config['DAILY_SCHEDULE_DF'] = pd.DataFrame()
app.config['PROCESSED'] = False

def run_analysis():
    try:

        # Get all PDF files
        from pdf_utils import get_all_pdf_files
        from config import LECTURE_SLIDES_FOLDER, QUESTIONS_FOLDER
        
        lecture_files = get_all_pdf_files(LECTURE_SLIDES_FOLDER)
        question_files = get_all_pdf_files(QUESTIONS_FOLDER)
        
        if not lecture_files:
            return False, "No lecture slides found!"
        
        # Process lectures
        lecture_data = []
        all_mcq_data = []
        
        for i, lecture_file in enumerate(lecture_files):
            # Extract lecture text
            from pdf_utils import extract_text_from_pdf, extract_lecture_title, find_matching_question_file
            from nlp_utils import extract_topics_from_text
            from mcq_utils import extract_questions_from_pdf, create_mcq_dataframe
            from config import N_TOPICS, MAX_SENTENCES_PER_LECTURE
            
            lecture_text = extract_text_from_pdf(lecture_file)
            lecture_title = extract_lecture_title(lecture_text)
            
            topics = extract_topics_from_text(lecture_text, n_topics=N_TOPICS,
                                              max_sentences=MAX_SENTENCES_PER_LECTURE)
            
            matching_question_file = find_matching_question_file(lecture_file, question_files)
            
            questions = []
            if matching_question_file:
                question_text = extract_text_from_pdf(matching_question_file)
                questions = extract_questions_from_pdf(question_text, use_openai_for_answers=False)
                
                lecture_id = f"lec_{i + 1}"
                if questions:
                    mcq_df = create_mcq_dataframe(questions, lecture_id)
                    all_mcq_data.append(mcq_df)
                    print(f"   Extracted {len(questions)} questions")
            
            lecture_data.append({
                'id': f"lec_{i + 1}",
                'file': lecture_file,
                'filename': os.path.basename(lecture_file),
                'title': lecture_title,
                'topics': topics,
                'question_file': matching_question_file,
                'question_filename': os.path.basename(matching_question_file) if matching_question_file else None,
                'question_count': len(questions)
            })
        
        # Combine all MCQ data
        if all_mcq_data:
            mcq_df = pd.concat(all_mcq_data, ignore_index=True)
        else:
            mcq_df = pd.DataFrame(columns=['id', 'lecture_id', 'question', 'options', 'source'])
        
        # Combine all topics
        all_topics = []
        topic_counter = 0
        for lecture in lecture_data:
            if 'topics' in lecture:
                for topic in lecture['topics']:
                    topic['topic_id'] = topic_counter
                    topic['lecture_id'] = lecture['id']
                    all_topics.append(topic)
                    topic_counter += 1
        
        # Analyze question distribution
        from analysis_utils import analyze_question_distribution
        percentage_df = analyze_question_distribution(lecture_data, question_files)
        
        # Generate detailed report
        from analysis_utils import generate_detailed_question_report
        detailed_report = generate_detailed_question_report(lecture_data, mcq_df)
        
        # Create visualization
        try:
            from main import create_percentage_visualization
            create_percentage_visualization(percentage_df, os.path.join(app.config['OUTPUT_FOLDER'], 'question_percentage_chart.png'))
        except:

            import matplotlib.pyplot as plt
            plt.figure(figsize=(12, 8))
            
            # Bar chart
            plt.subplot(2, 1, 1)
            lectures = percentage_df['Lecture_File'].tolist()
            percentages = percentage_df['Percentage_of_Total'].tolist()
            x_pos = range(len(lectures))
            bars = plt.bar(x_pos, percentages, color='skyblue', edgecolor='black')
            plt.xticks(x_pos, lectures, rotation=45, ha='right')
            plt.ylabel('Percentage of Total Questions (%)')
            plt.title('Question Distribution Across Lectures')
            plt.grid(True, alpha=0.3)
            
            # Cumulative line chart
            plt.subplot(2, 1, 2)
            cumulative_percentages = percentage_df['Cumulative_Percentage'].tolist()
            plt.plot(x_pos, cumulative_percentages, 'o-', color='darkgreen', linewidth=2, markersize=8)
            plt.fill_between(x_pos, 0, cumulative_percentages, alpha=0.2, color='green')
            plt.xticks(x_pos, lectures, rotation=45, ha='right')
            plt.ylabel('Cumulative Percentage (%)')
            plt.xlabel('Lecture Files')
            plt.title('Cumulative Question Coverage')
            plt.grid(True, alpha=0.3)
            plt.ylim([0, 110])
            
            plt.tight_layout()
            plt.savefig(os.path.join(app.config['OUTPUT_FOLDER'], 'question_percentage_chart.png'), dpi=150, bbox_inches='tight')
            plt.close()
        
        # Store in app config
        app.config['LECTURE_DATA'] = lecture_data
        app.config['MCQ_DF'] = mcq_df
        app.config['PERCENTAGE_DF'] = percentage_df
        app.config['ALL_TOPICS'] = all_topics
        app.config['DETAILED_REPORT'] = detailed_report
        app.config['PROCESSED'] = True
        
        return True, "Analysis completed successfully!"
        
    except Exception as e:
        traceback.print_exc()
        return False, str(e)

def generate_study_plan_pdf(study_plan_df, daily_schedule_df, total_hours, study_days):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30,
        alignment=1
    )
    story.append(Paragraph("Personalized Study Plan", title_style))
    story.append(Spacer(1, 12))

    # Study info
    info_style = ParagraphStyle(
        'InfoStyle',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=6
    )
    story.append(Paragraph(f"Total Study Hours: {total_hours}", info_style))
    story.append(Paragraph(f"Study Days: {study_days}", info_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", info_style))
    story.append(Spacer(1, 20))

    # Study Plan Table
    story.append(Paragraph("Recommended Study Focus", styles['Heading2']))
    story.append(Spacer(1, 10))

    table_data = [['Priority', 'Lecture', 'Question %', 'Hours', 'Focus']]
    for _, row in study_plan_df.iterrows():
        # Safely convert Question_Percentage to float
        question_percentage = row['Question_Percentage']
        if isinstance(question_percentage, str):
            try:
                question_percentage = float(question_percentage.replace('%', ''))
            except:
                question_percentage = 0.0
        else:
            question_percentage = float(question_percentage) if question_percentage else 0.0
        
        # Safely convert Recommended_Hours to float
        recommended_hours = row['Recommended_Hours']
        if isinstance(recommended_hours, str):
            try:
                recommended_hours = float(recommended_hours)
            except:
                recommended_hours = 0.0
        else:
            recommended_hours = float(recommended_hours) if recommended_hours else 0.0
        
        table_data.append([
            str(row['Priority']),
            row['Lecture'][:30] + '...' if len(row['Lecture']) > 30 else row['Lecture'],
            f"{question_percentage:.1f}%",
            f"{recommended_hours:.1f}h",
            row['Focus_Intensity']
        ])

    table = Table(table_data, colWidths=[0.5*inch, 2.5*inch, 1*inch, 0.8*inch, 1*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    # Daily Schedule
    story.append(Paragraph("Daily Study Schedule", styles['Heading2']))
    story.append(Spacer(1, 10))

    schedule_data = [['Day', 'Date', 'Lectures', 'Hours']]
    for _, row in daily_schedule_df.iterrows():
        # Safely convert Total_Hours to float
        total_hours_val = row['Total_Hours']
        if isinstance(total_hours_val, str):
            try:
                total_hours_val = float(total_hours_val)
            except:
                total_hours_val = 0.0
        else:
            total_hours_val = float(total_hours_val) if total_hours_val else 0.0
        
        schedule_data.append([
            str(row['Day']),
            row['Date'],
            row['Lectures'][:40] + '...' if len(row['Lectures']) > 40 else row['Lectures'],
            f"{total_hours_val:.1f}h"
        ])

    schedule_table = Table(schedule_data, colWidths=[0.5*inch, 1.2*inch, 3*inch, 0.8*inch])
    schedule_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.lightcyan),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    story.append(schedule_table)

    doc.build(story)
    buffer.seek(0)
    return buffer


@app.route('/')
def index():
    stats = {
        'total_lectures': len(app.config['LECTURE_DATA']),
        'total_questions': len(app.config['MCQ_DF']) if not app.config['MCQ_DF'].empty else 0,
        'total_topics': len(app.config['ALL_TOPICS']),
        'processed': app.config['PROCESSED']
    }

    # Create frequency analysis visualization
    freq_chart = None
    pie_chart = None

    if not app.config['PERCENTAGE_DF'].empty:
        # Bar chart
        fig = px.bar(
            app.config['PERCENTAGE_DF'],
            x='Lecture_File',
            y='Percentage_of_Total',
            title='Question Distribution by Lecture',
            labels={'Percentage_of_Total': 'Percentage (%)', 'Lecture_File': 'Lecture'},
            color='Percentage_of_Total',
            color_continuous_scale='Viridis'
        )
        fig.update_layout(xaxis_tickangle=-45)
        freq_chart = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

        # Pie chart
        fig2 = px.pie(
            app.config['PERCENTAGE_DF'],
            values='Questions_In_Lecture',
            names='Lecture_File',
            title='Question Count Distribution'
        )
        pie_chart = json.dumps(fig2, cls=plotly.utils.PlotlyJSONEncoder)

    return render_template('index.html', 
                          stats=stats, 
                          freq_chart=freq_chart,
                          pie_chart=pie_chart,
                          percentage_df=app.config['PERCENTAGE_DF'].to_dict('records') if not app.config['PERCENTAGE_DF'].empty else [])

@app.route('/run-analysis', methods=['POST'])
def run_analysis_route():
    success, message = run_analysis()
    if success:
        flash(message, 'success')
    else:
        flash(f'Error: {message}', 'error')
    return jsonify({'success': success, 'message': message})

@app.route('/study-plan', methods=['GET', 'POST'])
def study_plan():
    if request.method == 'POST':
        total_hours = float(request.form.get('total_hours', 20))
        study_days = int(request.form.get('study_days', 7))

        if not app.config['PERCENTAGE_DF'].empty:
            # Use your existing function
            from analysis_utils import generate_study_plan_based_on_percentage
            study_plan_df, daily_schedule_df = generate_study_plan_based_on_percentage(
                app.config['PERCENTAGE_DF'], total_hours, study_days
            )

            # Ensure numeric columns are proper types
            study_plan_df['Recommended_Hours'] = pd.to_numeric(study_plan_df['Recommended_Hours'], errors='coerce')
            
            # Make sure Question_Percentage is numeric (remove % if present)
            if 'Question_Percentage' in study_plan_df.columns:
                if study_plan_df['Question_Percentage'].dtype == 'object':
                    study_plan_df['Question_Percentage'] = study_plan_df['Question_Percentage'].astype(str).str.replace('%', '').astype(float)
            
            app.config['STUDY_PLAN_DF'] = study_plan_df
            app.config['DAILY_SCHEDULE_DF'] = daily_schedule_df
            app.config['TOTAL_HOURS'] = total_hours
            app.config['STUDY_DAYS'] = study_days

            # Create visualization
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=study_plan_df['Lecture'],
                y=study_plan_df['Recommended_Hours'],
                name='Study Hours',
                marker_color='lightblue'
            ))
            fig.update_layout(
                title='Recommended Study Hours per Lecture',
                xaxis_tickangle=-45,
                height=500
            )
            hours_chart = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)

            return render_template('study_plan.html',
                                 study_plan=study_plan_df.to_dict('records'),
                                 daily_schedule=daily_schedule_df.to_dict('records'),
                                 hours_chart=hours_chart,
                                 total_hours=total_hours,
                                 study_days=study_days)

    return render_template('study_plan.html', 
                          study_plan=None,
                          daily_schedule=None)

@app.route('/download-study-plan-pdf')
def download_study_plan_pdf():
    if app.config['STUDY_PLAN_DF'].empty or app.config['DAILY_SCHEDULE_DF'].empty:
        flash('No study plan data available. Please generate a study plan first.', 'error')
        return redirect(url_for('study_plan'))

    # Get parameters from URL or use stored values
    total_hours = request.args.get('total_hours')
    study_days = request.args.get('study_days')
    
    # If not in URL, try to get from app config
    if total_hours is None:
        total_hours = app.config.get('TOTAL_HOURS', 20)
    else:
        total_hours = float(total_hours)
        
    if study_days is None:
        study_days = app.config.get('STUDY_DAYS', 7)
    else:
        study_days = int(study_days)
    
    # Make a copy of the dataframes to avoid modifying the original
    study_plan_df = app.config['STUDY_PLAN_DF'].copy()
    daily_schedule_df = app.config['DAILY_SCHEDULE_DF'].copy()
    
    # Ensure data is properly formatted for PDF
    if 'Question_Percentage' in study_plan_df.columns:
        if study_plan_df['Question_Percentage'].dtype == 'object':
            study_plan_df['Question_Percentage'] = study_plan_df['Question_Percentage'].astype(str).str.replace('%', '').astype(float)
    
    pdf_buffer = generate_study_plan_pdf(
        study_plan_df, 
        daily_schedule_df,
        total_hours,
        study_days
    )

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f'study_plan_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf',
        mimetype='application/pdf'
    )

@app.route('/priority-questions', methods=['GET', 'POST'])
def priority_questions():
    if app.config['PERCENTAGE_DF'].empty or not app.config['LECTURE_DATA']:
        flash('Please run analysis first', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        # Handle quiz submission
        student_answers = {}
        
        # Collect all answers from form
        for key, value in request.form.items():
            if key.startswith('question_'):
                question_id = key.replace('question_', '')
                student_answers[question_id] = value
        
        # Get correct answers from session
        correct_answers = session.get('correct_answers', {})
        
        # Backend validation: Check if all questions are answered
        total_expected = len(correct_answers)
        total_answered = len(student_answers)
        
        if total_answered != total_expected:
            flash(f'Please answer all {total_expected} questions before submitting. You have answered {total_answered} questions.', 'warning')
            return redirect(url_for('priority_questions'))
        
        # Evaluate answers
        results = evaluate_answers(student_answers, correct_answers)
        
        # Store results in session
        session['quiz_results'] = results
        session['quiz_completed'] = True
        
        flash('Quiz completed successfully!', 'success')
        return redirect(url_for('student_progress'))

    # GET request - show quiz questions
    # Use your existing function to extract questions
    from main import extract_questions_from_top_priorities
    extracted_questions = extract_questions_from_top_priorities(
        app.config['LECTURE_DATA'], 
        app.config['PERCENTAGE_DF'], 
        num_priorities=4, 
        total_questions=28
    )

    # Prepare questions for quiz format
    quiz_questions = prepare_quiz_questions(extracted_questions)
    
    # Store correct answers in session
    correct_answers = {}
    for q in quiz_questions:
        correct_answers[q['question_id']] = q['correct_answer']
    session['correct_answers'] = correct_answers

    return render_template('priority_questions.html', 
                         questions=quiz_questions,
                         total_questions=len(quiz_questions))

@app.route('/student-progress')
def student_progress():
    if not session.get('quiz_completed'):
        flash('Please complete the quiz first', 'warning')
        return redirect(url_for('priority_questions'))
    
    results = session.get('quiz_results', {})
    
    return render_template('student_progress.html', results=results)

@app.route('/graph-view')
def graph_view():
    import os
    
    # Check if graph exists in static folder first
    static_graph_path = os.path.join('static', 'lecture_recommendation_graph.html')
    root_graph_path = os.path.join('outputs', 'lecture_recommendation_graph.html')
    
    if os.path.exists(static_graph_path):
        # Use static folder version for better serving
        return render_template('graph_view.html', graph_path='static/lecture_recommendation_graph.html')
    elif os.path.exists(root_graph_path):
        # Fall back to outputs folder
        return render_template('graph_view.html', graph_path=root_graph_path)
    else:
        # No graph available
        return render_template('graph_view.html', graph_path=None)

@app.route('/api/stats')
def api_stats():
    return jsonify({
        'total_lectures': len(app.config['LECTURE_DATA']),
        'total_questions': len(app.config['MCQ_DF']),
        'total_topics': len(app.config['ALL_TOPICS']),
        'processed': app.config['PROCESSED']
    })

@app.route('/api/lecture-distribution')
def api_lecture_distribution():
    """API endpoint for lecture distribution data"""
    if app.config['PERCENTAGE_DF'].empty:
        return jsonify([])
    return jsonify(app.config['PERCENTAGE_DF'].to_dict('records'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
