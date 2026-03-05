"""MCQ Study Plan business logic - wraps root-level modules."""
import os
import sys
import io
import traceback
from datetime import datetime
from pathlib import Path

# Ensure service root is in path for pdf_utils, config, etc.
SERVICE_ROOT = Path(__file__).resolve().parents[2]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

# State is updated via app.services.state

OUTPUT_FOLDER = "outputs"


def run_analysis() -> tuple[bool, str]:
    """Run lecture/question analysis. Returns (success, message)."""
    try:
        from pdf_utils import get_all_pdf_files
        from config import LECTURE_SLIDES_FOLDER, QUESTIONS_FOLDER

        lecture_files = get_all_pdf_files(LECTURE_SLIDES_FOLDER)
        question_files = get_all_pdf_files(QUESTIONS_FOLDER)

        if not lecture_files:
            return False, "No lecture slides found!"

        from pdf_utils import extract_text_from_pdf, extract_lecture_title, find_matching_question_file
        from nlp_utils import extract_topics_from_text
        from mcq_utils import extract_questions_from_pdf, create_mcq_dataframe
        from config import N_TOPICS, MAX_SENTENCES_PER_LECTURE
        from analysis_utils import analyze_question_distribution, generate_detailed_question_report

        lecture_data = []
        all_mcq_data = []

        for i, lecture_file in enumerate(lecture_files):
            lecture_text = extract_text_from_pdf(lecture_file)
            lecture_title = extract_lecture_title(lecture_text)
            topics = extract_topics_from_text(lecture_text, n_topics=N_TOPICS, max_sentences=MAX_SENTENCES_PER_LECTURE)
            matching_question_file = find_matching_question_file(lecture_file, question_files)
            questions = []
            if matching_question_file:
                question_text = extract_text_from_pdf(matching_question_file)
                questions = extract_questions_from_pdf(question_text, use_openai_for_answers=False)
                lecture_id = f"lec_{i + 1}"
                if questions:
                    mcq_df = create_mcq_dataframe(questions, lecture_id)
                    all_mcq_data.append(mcq_df)

            lecture_data.append({
                "id": f"lec_{i + 1}",
                "file": lecture_file,
                "filename": os.path.basename(lecture_file),
                "title": lecture_title,
                "topics": topics,
                "question_file": matching_question_file,
                "question_filename": os.path.basename(matching_question_file) if matching_question_file else None,
                "question_count": len(questions),
            })

        if all_mcq_data:
            mcq_df = pd.concat(all_mcq_data, ignore_index=True)
        else:
            mcq_df = pd.DataFrame(columns=["id", "lecture_id", "question", "options", "source"])

        all_topics = []
        topic_counter = 0
        for lecture in lecture_data:
            if "topics" in lecture:
                for topic in lecture["topics"]:
                    topic["topic_id"] = topic_counter
                    topic["lecture_id"] = lecture["id"]
                    all_topics.append(topic)
                    topic_counter += 1

        percentage_df = analyze_question_distribution(lecture_data, question_files)
        detailed_report = generate_detailed_question_report(lecture_data, mcq_df)

        try:
            from main import create_percentage_visualization
            create_percentage_visualization(percentage_df, os.path.join(OUTPUT_FOLDER, "question_percentage_chart.png"))
        except Exception:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            plt.figure(figsize=(12, 8))
            lectures = percentage_df["Lecture_File"].tolist()
            percentages = percentage_df["Percentage_of_Total"].tolist()
            x_pos = range(len(lectures))
            plt.subplot(2, 1, 1)
            plt.bar(x_pos, percentages, color="skyblue", edgecolor="black")
            plt.xticks(x_pos, lectures, rotation=45, ha="right")
            plt.ylabel("Percentage of Total Questions (%)")
            plt.title("Question Distribution Across Lectures")
            plt.grid(True, alpha=0.3)
            plt.subplot(2, 1, 2)
            cumulative = percentage_df["Cumulative_Percentage"].tolist()
            plt.plot(x_pos, cumulative, "o-", color="darkgreen", linewidth=2, markersize=8)
            plt.fill_between(x_pos, 0, cumulative, alpha=0.2, color="green")
            plt.xticks(x_pos, lectures, rotation=45, ha="right")
            plt.ylabel("Cumulative Percentage (%)")
            plt.xlabel("Lecture Files")
            plt.title("Cumulative Question Coverage")
            plt.grid(True, alpha=0.3)
            plt.ylim([0, 110])
            plt.tight_layout()
            plt.savefig(os.path.join(OUTPUT_FOLDER, "question_percentage_chart.png"), dpi=150, bbox_inches="tight")
            plt.close()

        # Build graph (optional - skip if fails)
        graph_path = os.path.join(OUTPUT_FOLDER, "lecture_recommendation_graph.html")
        if not mcq_df.empty and all_topics:
            try:
                from mcq_utils import compute_similarities
                from graph_utils import build_pyvis_graph
                sims, _ = compute_similarities(all_topics, mcq_df)
                build_pyvis_graph(lecture_data, mcq_df, sims, graph_path, open_browser=False)
            except Exception as graph_err:
                print(f"Graph build skipped: {graph_err}")

        # Update state
        import app.services.state as st
        st.LECTURE_DATA.clear()
        st.LECTURE_DATA.extend(lecture_data)
        st.MCQ_DF = mcq_df
        st.PERCENTAGE_DF = percentage_df
        st.ALL_TOPICS.clear()
        st.ALL_TOPICS.extend(all_topics)
        st.DETAILED_REPORT = detailed_report
        st.PROCESSED = True

        return True, "Analysis completed successfully!"

    except Exception as e:
        traceback.print_exc()
        return False, str(e)


def generate_study_plan_pdf(study_plan_df: pd.DataFrame, daily_schedule_df: pd.DataFrame, total_hours: float, study_days: int) -> io.BytesIO:
    """Generate PDF bytes for study plan."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)
    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontSize=24, spaceAfter=30, alignment=1)
    story.append(Paragraph("Personalized Study Plan", title_style))
    story.append(Spacer(1, 12))
    info_style = ParagraphStyle("InfoStyle", parent=styles["Normal"], fontSize=12, spaceAfter=6)
    story.append(Paragraph(f"Total Study Hours: {total_hours}", info_style))
    story.append(Paragraph(f"Study Days: {study_days}", info_style))
    story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", info_style))
    story.append(Spacer(1, 20))

    story.append(Paragraph("Recommended Study Focus", styles["Heading2"]))
    story.append(Spacer(1, 10))
    table_data = [["Priority", "Lecture", "Question %", "Hours", "Focus"]]
    for _, row in study_plan_df.iterrows():
        pct = row.get("Question_Percentage", 0)
        if isinstance(pct, str):
            try:
                pct = float(pct.replace("%", ""))
            except Exception:
                pct = 0.0
        else:
            pct = float(pct) if pct else 0.0
        hrs = row.get("Recommended_Hours", 0)
        if isinstance(hrs, str):
            try:
                hrs = float(hrs)
            except Exception:
                hrs = 0.0
        else:
            hrs = float(hrs) if hrs else 0.0
        table_data.append([
            str(row["Priority"]),
            (row["Lecture"][:30] + "...") if len(row["Lecture"]) > 30 else row["Lecture"],
            f"{pct:.1f}%",
            f"{hrs:.1f}h",
            row["Focus_Intensity"],
        ])

    table = Table(table_data, colWidths=[0.5 * inch, 2.5 * inch, 1 * inch, 0.8 * inch, 1 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))

    story.append(Paragraph("Daily Study Schedule", styles["Heading2"]))
    story.append(Spacer(1, 10))
    schedule_data = [["Day", "Date", "Lectures", "Hours"]]
    for _, row in daily_schedule_df.iterrows():
        th = row.get("Total_Hours", 0)
        if isinstance(th, str):
            try:
                th = float(th)
            except Exception:
                th = 0.0
        else:
            th = float(th) if th else 0.0
        schedule_data.append([
            str(row["Day"]),
            row["Date"],
            (row["Lectures"][:40] + "...") if len(row["Lectures"]) > 40 else row["Lectures"],
            f"{th:.1f}h",
        ])

    schedule_table = Table(schedule_data, colWidths=[0.5 * inch, 1.2 * inch, 3 * inch, 0.8 * inch])
    schedule_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.lightcyan),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
    ]))
    story.append(schedule_table)
    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_adaptive_outputs(adaptive_plan_df: pd.DataFrame, baseline_plan_df: pd.DataFrame) -> None:
    """Generate CSV and chart outputs for adaptive plan."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        baseline_csv = os.path.join(OUTPUT_FOLDER, "baseline_study_plan.csv")
        adaptive_csv = os.path.join(OUTPUT_FOLDER, "adaptive_study_plan.csv")
        baseline_plan_df.to_csv(baseline_csv, index=False)
        adaptive_plan_df.to_csv(adaptive_csv, index=False)

        lectures = adaptive_plan_df["Lecture"].tolist()
        baseline_hours = []
        adaptive_hours = []
        deltas = []
        for _, ar in adaptive_plan_df.iterrows():
            br = baseline_plan_df[baseline_plan_df["Lecture"] == ar["Lecture"]].iloc[0]
            baseline_hours.append(float(br["Recommended_Hours"]))
            adaptive_hours.append(float(ar["Adaptive_Hours"]))
            deltas.append(float(ar["Delta_Hours"]))

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))
        x = range(len(lectures))
        w = 0.35
        ax1.bar([i - w / 2 for i in x], baseline_hours, w, label="Baseline", color="lightblue", alpha=0.8)
        ax1.bar([i + w / 2 for i in x], adaptive_hours, w, label="Adaptive", color="orange", alpha=0.8)
        ax1.set_xlabel("Lectures")
        ax1.set_ylabel("Study Hours")
        ax1.set_title("Baseline vs Adaptive Study Hours")
        ax1.set_xticks(x)
        ax1.set_xticklabels(lectures, rotation=45, ha="right")
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        cols = ["green" if d > 0 else "red" for d in deltas]
        ax2.bar(x, deltas, color=cols, alpha=0.7)
        ax2.set_xlabel("Lectures")
        ax2.set_ylabel("Delta Hours")
        ax2.set_title("Study Plan Shift")
        ax2.set_xticks(x)
        ax2.set_xticklabels(lectures, rotation=45, ha="right")
        ax2.axhline(y=0, color="black", linestyle="-", alpha=0.5)
        ax2.grid(True, alpha=0.3)
        for i, d in enumerate(deltas):
            ax2.text(i, d + (0.1 if d >= 0 else -0.1), f"{d:+.1f}", ha="center", va="bottom" if d >= 0 else "top")
        plt.tight_layout()
        plt.savefig(os.path.join(OUTPUT_FOLDER, "study_plan_shift_chart.png"), dpi=150, bbox_inches="tight")
        plt.close()
    except Exception as e:
        print(f"Error generating adaptive outputs: {e}")
