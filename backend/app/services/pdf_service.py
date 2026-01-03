from fpdf import FPDF
from datetime import datetime
from pathlib import Path

class PDFService:
    @staticmethod
    def _sanitize_text(text: str) -> str:
        """
        Replaces characters not supported by standard PDF fonts (Latin-1).
        """
        if not text:
            return ""
        replacements = {
            "→": "->",
            "\u2192": "->", # specifically the arrow
            "•": "-",
            "\u2022": "-",
            "“": "\"",
            "”": "\"",
            "‘": "'",
            "’": "'",
            "–": "-",
            "—": "--",
        }
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        return text

    @staticmethod
    def generate_pdf(paper_data: dict, output_path: str):
        """
        Converts the paper JSON data into a professional PDF.
        """
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # --- Page 1: COVER PAGE ---
        pdf.add_page()
        pdf.set_font("helvetica", "B", 24)
        pdf.ln(80)
        pdf.cell(0, 10, "AI-GENERATED MODEL PAPER", ln=True, align="C")
        
        pdf.set_font("helvetica", "", 16)
        pdf.ln(10)
        subject = PDFService._sanitize_text("Database Management Systems")
        pdf.cell(0, 10, f"Subject: {subject}", ln=True, align="C")
        
        pdf.set_font("helvetica", "I", 12)
        pdf.ln(20)
        raw_gen_time = paper_data.get("generated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        gen_time = PDFService._sanitize_text(raw_gen_time)
        pdf.cell(0, 10, f"Generated on: {gen_time}", ln=True, align="C")
        pdf.cell(0, 10, f"Total Marks: {paper_data.get('total_marks', 100)}", ln=True, align="C")
        
        pdf.ln(100)
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 10, "Copyright (c) 2025 SLIIT Students Project. All rights reserved.", ln=True, align="C")
        
        # --- Page 2 onwards: CONTENT ---
        pdf.add_page()
        pdf.set_font("helvetica", "B", 16)
        pdf.cell(0, 10, "Examination Paper", ln=True, align="L")
        pdf.ln(5)
        
        questions = paper_data.get("questions", [])
        for q in questions:
            q_no = q.get("question_no", "?")
            total_q_marks = q.get("marks", 0)
            
            # Question Header
            pdf.set_font("helvetica", "B", 12)
            pdf.ln(10)
            pdf.cell(0, 10, f"Question {q_no} ({total_q_marks} marks)", ln=True)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + 190, pdf.get_y())
            pdf.ln(2)
            
            # Sub-questions
            subquestions = q.get("subquestions", [])
            if subquestions:
                for sq in subquestions:
                    label = PDFService._sanitize_text(sq.get("label", ""))
                    text = PDFService._sanitize_text(sq.get("text", ""))
                    marks = sq.get("marks", 0)
                    
                    pdf.set_font("helvetica", "", 11)
                    pdf.ln(3)  # Add spacing before each sub-question
                    
                    # Print label and text on the same line
                    pdf.set_x(15)
                    full_text = f"{label})  {text}"
                    
                    # Use multi_cell for the full text (handles wrapping)
                    pdf.multi_cell(155, 6, full_text)
                    
                    # Now place the marks on the right side of the LAST line
                    # We need to go back up to align with the last line of text
                    current_y = pdf.get_y()
                    pdf.set_y(current_y - 6)  # Move up one line height
                    pdf.set_x(175)
                    pdf.set_font("helvetica", "I", 10)
                    pdf.cell(20, 6, f"({int(marks)})", align="R")
                    
                    # Reset Y to continue below
                    pdf.set_y(current_y)
                    pdf.ln(2)  # Small gap between sub-questions
            else:
                # Fallback for monolithic text
                text = PDFService._sanitize_text(q.get("text", "No content available."))
                pdf.set_font("helvetica", "", 11)
                pdf.multi_cell(0, 7, text)
                pdf.ln(5)
        
        # Final Save
        pdf.output(output_path)
        print(f"PDF successfully exported to: {output_path}")
