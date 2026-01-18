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
                    
                    # Use multi_cell for the full text (handles wrapping)
                    if "```mermaid" in text:
                        # Split text into description and mermaid code
                        parts = text.split("```mermaid")
                        desc = parts[0].strip()
                        mermaid = "```mermaid" + parts[1]
                        
                        pdf.multi_cell(155, 6, f"{label})  {desc}")
                        pdf.set_font("courier", "I", 9)
                        pdf.ln(2)
                        pdf.set_x(25)
                        pdf.multi_cell(145, 5, mermaid)
                        pdf.set_font("helvetica", "", 11)
                    else:
                        pdf.multi_cell(155, 6, f"{label})  {text}")
                    
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

            # --- DIAGRAM RENDERING (V2) ---
            # Check if we have mermaid code to render
            mermaid_code = q.get("mermaid_code")
            needs_diagram = q.get("needs_diagram", False)
            
            # Decide: Render if mermaid code exists
            if mermaid_code:
                try:
                    from app.services.diagram_service import DiagramService
                    import os
                    
                    # Generate temporary path
                    timestamp = int(datetime.now().timestamp())
                    temp_img_path = str(Path(output_path).parent / "temp_images" / f"q_{q_no}_{timestamp}.png")
                    
                    print(f"    🎨 Rendering diagram for {q_no}...")
                    success = DiagramService.render_mermaid_to_image(mermaid_code, temp_img_path)
                    
                    if success and os.path.exists(temp_img_path):
                        pdf.ln(5)
                        pdf.set_font("helvetica", "B", 10)
                        diagram_type = q.get("diagram_type", "Diagram")
                        pdf.cell(0, 10, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                        
                        # Calculate available width (A4 width - margins)
                        avail_width = 180 
                        # Embed image (auto-scale)
                        pdf.image(temp_img_path, w=avail_width)
                        pdf.ln(5)
                    else:
                        # Fallback to text if rendering failed
                        raise Exception("Rendering failed")
                        
                except Exception as e:
                    print(f"    ⚠️ Diagram rendering failed: {e}. Using placeholder.")
                    # Fallback Placeholder
                    pdf.ln(5)
                    pdf.set_fill_color(240, 240, 240)
                    pdf.rect(20, pdf.get_y(), 170, 30, 'FD')
                    pdf.set_xy(25, pdf.get_y()+10)
                    pdf.set_font("helvetica", "I", 10)
                    pdf.multi_cell(160, 5, f"[Diagram Generation Failed: {str(e)[:50]}...]\nMermaid code available in JSON.")
                    pdf.ln(20)
            
            # Legacy/Placeholder check (if no mermaid code but needs_diagram was set)
            elif needs_diagram:
                 # Standard Placeholder
                diagram_type = q.get("diagram_type", "Diagram")
                pdf.ln(5)
                pdf.set_fill_color(250, 250, 250)
                pdf.rect(20, pdf.get_y(), 170, 40, 'FD')
                pdf.set_xy(25, pdf.get_y()+15)
                pdf.set_font("helvetica", "I", 10)
                pdf.multi_cell(160, 6, f"[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram in the answer booklet.]", align="C")
                pdf.ln(25)
            
            # Legacy support: If mermaid_code exists but no placeholder, render as code (for backward compatibility)
            mermaid_code = q.get("mermaid_code")
            if mermaid_code and not needs_diagram:
                caption = q.get("image_caption", "Figure")
                pdf.ln(5)
                pdf.set_font("helvetica", "B", 10)
                pdf.cell(0, 10, PDFService._sanitize_text(caption), ln=True)
                
                pdf.set_fill_color(245, 245, 245) # Light gray background
                pdf.set_font("courier", "", 9)
                
                # Split lines for rendering
                code_lines = mermaid_code.split("\n")
                for line in code_lines:
                    # Sanitize line
                    safe_line = PDFService._sanitize_text(line)
                    pdf.set_x(20)
                    pdf.cell(0, 5, safe_line, ln=True, fill=True)
                
                pdf.ln(5)
        
        # Final Save
        pdf.output(output_path)
        print(f"PDF successfully exported to: {output_path}")
