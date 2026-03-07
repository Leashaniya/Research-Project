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

# CORS for React frontend (port 5173)
@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', 'http://localhost:5173')
    response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

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


# ============= REST API for React Frontend =============

@app.route('/api/')
@app.route('/api/dashboard/')
def api_health():
    """Health check for React frontend"""
    return jsonify({'status': 'ok', 'service': 'mcq-study-plan'})

@app.route('/api/dashboard/stats')
def api_dashboard_stats():
    """Dashboard stats in format expected by React mcqApi"""
    pct_df = app.config['PERCENTAGE_DF']
    total_lectures = len(app.config['LECTURE_DATA'])
    total_questions = len(app.config['MCQ_DF']) if not app.config['MCQ_DF'].empty else 0
    high_priority = len(pct_df[pct_df['Percentage_of_Total'] > 10]) if not pct_df.empty else 0
    avg_per_lecture = round(total_questions / total_lectures, 1) if total_lectures > 0 else 0
    return jsonify({
        'total_lectures': total_lectures,
        'total_questions': total_questions,
        'avg_questions_per_lecture': avg_per_lecture,
        'high_priority_lectures': high_priority,
        'study_completion_percentage': 0,
        'processed': app.config['PROCESSED']
    })

@app.route('/api/dashboard/analyze', methods=['POST'])
def api_dashboard_analyze():
    """Run analysis - returns stats for React"""
    success, message = run_analysis()
    if not success:
        return jsonify({'success': False, 'message': message}), 400
    stats = {
        'total_lectures': len(app.config['LECTURE_DATA']),
        'total_questions': len(app.config['MCQ_DF']) if not app.config['MCQ_DF'].empty else 0,
        'avg_questions_per_lecture': 0,
        'high_priority_lectures': 0,
        'study_completion_percentage': 0,
        'processed': True
    }
    pct_df = app.config['PERCENTAGE_DF']
    if not pct_df.empty and stats['total_lectures'] > 0:
        stats['avg_questions_per_lecture'] = round(stats['total_questions'] / stats['total_lectures'], 1)
        stats['high_priority_lectures'] = len(pct_df[pct_df['Percentage_of_Total'] > 10])
    return jsonify({
        'success': True,
        'message': message,
        'stats': stats,
        'question_distribution_count': len(pct_df) if not pct_df.empty else 0,
        'total_lectures': stats['total_lectures'],
        'total_questions': stats['total_questions'],
        'percentage_df': pct_df.to_dict('records') if not pct_df.empty else []
    })

@app.route('/api/study-plan/generate', methods=['POST'])
def api_study_plan_generate():
    """Generate study plan - expects JSON {total_hours, study_days}"""
    if app.config['PERCENTAGE_DF'].empty:
        return jsonify({'error': 'Please run analysis first'}), 400
    data = request.get_json() or {}
    total_hours = float(data.get('total_hours', 20))
    study_days = int(data.get('study_days', 7))
    from analysis_utils import generate_study_plan_based_on_percentage
    study_plan_df, daily_schedule_df = generate_study_plan_based_on_percentage(
        app.config['PERCENTAGE_DF'], total_hours, study_days
    )
    app.config['STUDY_PLAN_DF'] = study_plan_df
    app.config['DAILY_SCHEDULE_DF'] = daily_schedule_df
    app.config['TOTAL_HOURS'] = total_hours
    app.config['STUDY_DAYS'] = study_days
    # Transform to React format
    plan_list = []
    for _, row in study_plan_df.iterrows():
        pct = row.get('Question_Percentage', 0)
        if isinstance(pct, str):
            pct = float(pct.replace('%', '')) if pct else 0
        plan_list.append({
            'priority': int(row['Priority']),
            'lecture': row['Lecture'],
            'focus_intensity': row['Focus_Intensity'],
            'recommended_hours': float(row['Recommended_Hours']),
            'questions': int(row.get('Question_Count', 0)),
            'percentage': pct
        })
    return jsonify(plan_list)

@app.route('/api/priority-questions')
def api_priority_questions():
    """Get priority questions for quiz - returns JSON for React"""
    if app.config['PERCENTAGE_DF'].empty or not app.config['LECTURE_DATA']:
        return jsonify({'error': 'Please run analysis first'}), 400
    from main import extract_questions_from_top_priorities
    extracted = extract_questions_from_top_priorities(
        app.config['LECTURE_DATA'], app.config['PERCENTAGE_DF'],
        num_priorities=4, total_questions=28
    )
    quiz_questions = prepare_quiz_questions(extracted)
    # Transform to React format
    result = []
    for q in quiz_questions:
        opts = q.get('options', [])
        if isinstance(opts, str):
            opts = [o.strip() for o in opts.split(' | ') if o.strip()]
        result.append({
            'id': q['question_id'],
            'question': q['question_text'],
            'options': opts,
            'answer': q.get('correct_answer', ''),
            'lecture': q.get('lecture', ''),
            'lecture_title': q.get('lecture_title', ''),
            'priority': q.get('priority', 0),
            'question_number': q.get('question_number', 0)
        })
    return jsonify(result)

@app.route('/api/quiz/submit', methods=['POST'])
def api_quiz_submit():
    """Submit quiz answers - returns evaluation results for React"""
    data = request.get_json() or {}
    student_answers = data.get('answers', {})
    correct_answers = data.get('correct_answers', {})
    if not student_answers or not correct_answers:
        return jsonify({'error': 'Missing answers or correct_answers'}), 400
    results = evaluate_answers(student_answers, correct_answers)
    # Build accuracy_by_lecture for adaptive plan (baseline uses Lecture_File e.g. "1.pdf")
    lecture_accuracy = {}
    for lecture, perf in results.get('topic_wise', {}).items():
        acc = perf.get('accuracy', 0)
        val = acc / 100.0 if acc > 1 else acc
        lecture_accuracy[lecture] = val
        # Also add with .pdf suffix for baseline matching (Lecture_File format)
        if not lecture.endswith('.pdf'):
            lecture_accuracy[f"{lecture}.pdf"] = val
    results['accuracy_by_lecture'] = lecture_accuracy
    results['overall_accuracy'] = results.get('accuracy', 0) / 100.0 if results.get('accuracy', 0) > 1 else results.get('accuracy', 0)
    return jsonify(results)

@app.route('/api/adaptive-plan/generate', methods=['POST'])
def api_adaptive_plan_generate():
    """Generate adaptive plan - expects quiz results in body (no session)"""
    if app.config['STUDY_PLAN_DF'].empty:
        return jsonify({'success': False, 'message': 'Generate baseline study plan first'}), 400
    data = request.get_json() or {}
    quiz_results = data.get('quiz_results', {})
    if not quiz_results:
        return jsonify({'success': False, 'message': 'Quiz results required'}), 400
    total_hours = float(data.get('total_hours', 20))
    study_days = int(data.get('study_days', 7))
    alpha = float(data.get('alpha', 0.5))
    max_increase = float(data.get('max_increase', 0.30))
    max_decrease = float(data.get('max_decrease', 0.15))
    from analysis_utils import generate_adaptive_study_plan
    adaptive_plan_df, adaptive_daily_df = generate_adaptive_study_plan(
        app.config['STUDY_PLAN_DF'], quiz_results, total_hours, study_days,
        alpha=alpha, max_increase=max_increase, max_decrease=max_decrease
    )
    if adaptive_plan_df.empty:
        return jsonify({'success': False, 'message': 'Failed to generate adaptive plan'}), 400
    app.config['ADAPTIVE_PLAN_DF'] = adaptive_plan_df
    app.config['ADAPTIVE_DAILY_DF'] = adaptive_daily_df
    app.config['ADAPTIVE_PARAMS'] = {
        'total_hours': total_hours, 'study_days': study_days,
        'alpha': alpha, 'max_increase': max_increase, 'max_decrease': max_decrease
    }
    generate_adaptive_outputs(adaptive_plan_df, app.config['STUDY_PLAN_DF'])
    adaptive_plan = []
    for _, row in adaptive_plan_df.iterrows():
        adaptive_plan.append({
            'Priority': row['Priority'],
            'Lecture': row['Lecture'],
            'Baseline_Hours': float(row['Baseline_Hours']),
            'Adaptive_Hours': float(row['Adaptive_Hours']),
            'Delta_Hours': float(row['Delta_Hours']),
            'Quiz_Accuracy': row['Quiz_Accuracy'],
            'Mastery_Gap': row['Mastery_Gap'],
            'Focus_Intensity': row['Focus_Intensity']
        })
    adaptive_daily = adaptive_daily_df.to_dict('records') if not adaptive_daily_df.empty else []
    return jsonify({
        'success': True,
        'adaptive_plan': adaptive_plan,
        'adaptive_daily': adaptive_daily,
        'params': app.config['ADAPTIVE_PARAMS']
    })

@app.route('/api/graph/url')
def api_graph_url():
    """Get graph HTML path for iframe (frontend prepends API base URL)"""
    import os
    if os.path.exists('static/lecture_recommendation_graph.html'):
        return jsonify({'url': '/static/lecture_recommendation_graph.html'})
    if os.path.exists('outputs/lecture_recommendation_graph.html'):
        return jsonify({'url': '/outputs/lecture_recommendation_graph.html'})
    return jsonify({'url': None})

@app.route('/api/download/study-plan-pdf')
def api_download_study_plan_pdf():
    """Download study plan PDF"""
    if app.config['STUDY_PLAN_DF'].empty or app.config['DAILY_SCHEDULE_DF'].empty:
        return jsonify({'error': 'No study plan available'}), 400
    total_hours = request.args.get('total_hours', app.config.get('TOTAL_HOURS', 20))
    study_days = request.args.get('study_days', app.config.get('STUDY_DAYS', 7))
    study_plan_df = app.config['STUDY_PLAN_DF'].copy()
    daily_schedule_df = app.config['DAILY_SCHEDULE_DF'].copy()
    pdf_buffer = generate_study_plan_pdf(study_plan_df, daily_schedule_df, float(total_hours), int(study_days))
    return send_file(pdf_buffer, as_attachment=True,
                     download_name=f'study_plan_{datetime.now().strftime("%Y%m%d_%H%M")}.pdf',
                     mimetype='application/pdf')

@app.route('/generate-adaptive-plan', methods=['POST'])
def generate_adaptive_plan():
    if not session.get('quiz_completed'):
        return jsonify({'success': False, 'message': 'Please complete the quiz first'})
    
    if app.config['STUDY_PLAN_DF'].empty:
        return jsonify({'success': False, 'message': 'No baseline study plan available. Please generate a study plan first.'})
    
    try:
        # Get parameters from request
        params = request.get_json()
        total_hours = float(params.get('total_hours', 20))
        study_days = int(params.get('study_days', 7))
        alpha = float(params.get('alpha', 0.5))
        max_increase = float(params.get('max_increase', 0.30))
        max_decrease = float(params.get('max_decrease', 0.15))
        
        # Get quiz results
        quiz_results = session.get('quiz_results', {})
        
        # Generate adaptive study plan
        from analysis_utils import generate_adaptive_study_plan
        adaptive_plan_df, adaptive_daily_df = generate_adaptive_study_plan(
            app.config['STUDY_PLAN_DF'],
            quiz_results,
            total_hours,
            study_days,
            alpha=alpha,
            max_increase=max_increase,
            max_decrease=max_decrease
        )
        
        if adaptive_plan_df.empty:
            return jsonify({'success': False, 'message': 'Failed to generate adaptive study plan'})
        
        # Store adaptive plan in app config
        app.config['ADAPTIVE_PLAN_DF'] = adaptive_plan_df
        app.config['ADAPTIVE_DAILY_DF'] = adaptive_daily_df
        app.config['ADAPTIVE_PARAMS'] = {
            'total_hours': total_hours,
            'study_days': study_days,
            'alpha': alpha,
            'max_increase': max_increase,
            'max_decrease': max_decrease
        }
        
        # Generate CSV outputs and shift chart
        generate_adaptive_outputs(adaptive_plan_df, app.config['STUDY_PLAN_DF'])
        
        return jsonify({'success': True, 'message': 'Adaptive study plan generated successfully'})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'Error generating adaptive study plan: {str(e)}'})

@app.route('/adaptive-study-plan')
def adaptive_study_plan():
    if app.config.get('ADAPTIVE_PLAN_DF') is None or app.config['ADAPTIVE_PLAN_DF'].empty:
        flash('No adaptive study plan available. Please generate one first.', 'error')
        return redirect(url_for('student_progress'))
    
    adaptive_plan_df = app.config['ADAPTIVE_PLAN_DF']
    adaptive_daily_df = app.config['ADAPTIVE_DAILY_DF']
    adaptive_params = app.config.get('ADAPTIVE_PARAMS', {})
    
    # Create visualization comparing baseline vs adaptive
    baseline_df = app.config['STUDY_PLAN_DF']
    
    fig = go.Figure()
    
    # Add baseline hours
    fig.add_trace(go.Bar(
        x=baseline_df['Lecture'],
        y=baseline_df['Recommended_Hours'],
        name='Baseline Hours',
        marker_color='lightblue'
    ))
    
    # Add adaptive hours
    fig.add_trace(go.Bar(
        x=adaptive_plan_df['Lecture'],
        y=adaptive_plan_df['Adaptive_Hours'],
        name='Adaptive Hours',
        marker_color='orange'
    ))
    
    fig.update_layout(
        title='Baseline vs Adaptive Study Hours Comparison',
        xaxis_tickangle=-45,
        barmode='group',
        height=500,
        xaxis_title='Lectures',
        yaxis_title='Study Hours'
    )
    
    comparison_chart = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
    
    return render_template('adaptive_study_plan.html',
                         adaptive_plan=adaptive_plan_df.to_dict('records'),
                         adaptive_daily=adaptive_daily_df.to_dict('records'),
                         comparison_chart=comparison_chart,
                         params=adaptive_params)

def generate_adaptive_outputs(adaptive_plan_df, baseline_plan_df):
    """Generate CSV outputs and shift chart for research purposes"""
    try:
        import matplotlib.pyplot as plt
        
        # Save baseline study plan CSV
        baseline_csv_path = os.path.join(app.config['OUTPUT_FOLDER'], 'baseline_study_plan.csv')
        baseline_plan_df.to_csv(baseline_csv_path, index=False)
        
        # Save adaptive study plan CSV
        adaptive_csv_path = os.path.join(app.config['OUTPUT_FOLDER'], 'adaptive_study_plan.csv')
        adaptive_plan_df.to_csv(adaptive_csv_path, index=False)
        
        # Generate shift chart
        create_shift_chart(adaptive_plan_df, baseline_plan_df)
        
        print(f"✓ Adaptive outputs generated:")
        print(f"  - Baseline CSV: {baseline_csv_path}")
        print(f"  - Adaptive CSV: {adaptive_csv_path}")
        print(f"  - Shift Chart: {os.path.join(app.config['OUTPUT_FOLDER'], 'study_plan_shift_chart.png')}")
        
    except Exception as e:
        print(f"Error generating adaptive outputs: {e}")

def create_shift_chart(adaptive_plan_df, baseline_plan_df):
    """Create shift chart comparing baseline vs adaptive hours"""
    import matplotlib.pyplot as plt
    
    # Prepare data
    lectures = adaptive_plan_df['Lecture'].tolist()
    baseline_hours = []
    adaptive_hours = []
    deltas = []
    
    for _, adaptive_row in adaptive_plan_df.iterrows():
        lecture = adaptive_row['Lecture']
        baseline_row = baseline_plan_df[baseline_plan_df['Lecture'] == lecture].iloc[0]
        
        baseline_hours.append(float(baseline_row['Recommended_Hours']))
        adaptive_hours.append(float(adaptive_row['Adaptive_Hours']))
        deltas.append(float(adaptive_row['Delta_Hours']))
    
    # Create the chart
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
    
    # Bar chart comparing baseline vs adaptive
    x = range(len(lectures))
    width = 0.35
    
    ax1.bar([i - width/2 for i in x], baseline_hours, width, label='Baseline Hours', color='lightblue', alpha=0.8)
    ax1.bar([i + width/2 for i in x], adaptive_hours, width, label='Adaptive Hours', color='orange', alpha=0.8)
    
    ax1.set_xlabel('Lectures')
    ax1.set_ylabel('Study Hours')
    ax1.set_title('Baseline vs Adaptive Study Hours Comparison')
    ax1.set_xticks(x)
    ax1.set_xticklabels(lectures, rotation=45, ha='right')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Delta chart
    colors = ['green' if delta > 0 else 'red' for delta in deltas]
    ax2.bar(x, deltas, color=colors, alpha=0.7)
    ax2.set_xlabel('Lectures')
    ax2.set_ylabel('Hour Difference (Adaptive - Baseline)')
    ax2.set_title('Study Plan Shift (Delta Hours)')
    ax2.set_xticks(x)
    ax2.set_xticklabels(lectures, rotation=45, ha='right')
    ax2.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax2.grid(True, alpha=0.3)
    
    # Add value labels on bars
    for i, delta in enumerate(deltas):
        ax2.text(i, delta + (0.1 if delta >= 0 else -0.1), 
                f'{delta:+.1f}', ha='center', va='bottom' if delta >= 0 else 'top')
    
    plt.tight_layout()
    plt.savefig(os.path.join(app.config['OUTPUT_FOLDER'], 'study_plan_shift_chart.png'), 
                dpi=150, bbox_inches='tight')
    plt.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
