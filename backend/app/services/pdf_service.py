from fpdf import FPDF
from datetime import datetime
from pathlib import Path
import os

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
            
            # Question Stem/Text (if exists and no subquestions, or as intro)
            question_stem = q.get("text", "")
            if question_stem and question_stem.strip():
                # Only show stem if it's substantial and not just a placeholder
                if len(question_stem.strip()) > 20:  # Substantial text
                    pdf.set_font("helvetica", "", 11)
                    pdf.ln(3)
                    pdf.multi_cell(0, 6, PDFService._sanitize_text(question_stem))
                    pdf.ln(3)
            
            # Show diagram immediately after question text (if generated)
            diagram_image_path = q.get("diagram_image_path")
            diagram_generated = q.get("diagram_generated", False)
            if diagram_generated and diagram_image_path:
                img_path_str = str(diagram_image_path) if isinstance(diagram_image_path, Path) else diagram_image_path
                img_path_normalized = img_path_str.replace("\\", "/")
                
                if os.path.exists(img_path_str):
                    try:
                        pdf.ln(3)
                        pdf.set_font("helvetica", "B", 10)
                        diagram_type = q.get("diagram_type", "Diagram")
                        pdf.cell(0, 10, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                        
                        # Calculate available width (A4 width - margins)
                        avail_width = 180
                        # Embed diagram image
                        pdf.image(img_path_normalized, w=avail_width)
                        pdf.ln(5)
                        print(f"    [OK] Embedded diagram image after question text: {img_path_normalized}")
                    except Exception as e:
                        print(f"    [WARN] Failed to embed diagram image: {e}")
                        import traceback
                        traceback.print_exc()
            
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

            # --- DIAGRAM RENDERING (V3: DALL·E + Mermaid Fallback) ---
            # Note: If diagram was already shown above (after question text), skip here
            # Priority 1: DALL·E generated image
            # Priority 2: Mermaid code rendering
            # Priority 3: Text placeholder
            
            diagram_image_path = q.get("diagram_image_path")
            diagram_image_url = q.get("diagram_image_url")
            mermaid_code = q.get("mermaid_code")
            needs_diagram = q.get("needs_diagram", False)
            diagram_generated = q.get("diagram_generated", False)
            diagram_placeholder = q.get("diagram_placeholder")
            
            # Skip diagram rendering here if it was already shown above (after question text)
            if diagram_generated and diagram_image_path:
                # Diagram already shown above, skip duplicate rendering
                pass
            # Priority 1: Generated diagram image (Graphviz or DALL·E) - only if not shown above
            elif diagram_image_path:
                # Convert to string and normalize path for FPDF (use forward slashes)
                img_path_str = str(diagram_image_path) if isinstance(diagram_image_path, Path) else diagram_image_path
                # Normalize path separators for FPDF (works on both Windows and Unix)
                img_path_normalized = img_path_str.replace("\\", "/")
                
                if os.path.exists(img_path_str):
                    try:
                        pdf.ln(5)
                        pdf.set_font("helvetica", "B", 10)
                        diagram_type = q.get("diagram_type", "Diagram")
                        pdf.cell(0, 10, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                        
                        # Calculate available width (A4 width - margins)
                        avail_width = 180
                        # Embed diagram image (FPDF.image accepts string path with forward slashes)
                        pdf.image(img_path_normalized, w=avail_width)
                        pdf.ln(5)
                        print(f"    [OK] Embedded diagram image: {img_path_normalized}")
                    except Exception as e:
                        print(f"    [WARN] Failed to embed diagram image: {e}")
                        import traceback
                        traceback.print_exc()
                        # Fall through to Mermaid or placeholder
                        diagram_image_path = None
                else:
                    print(f"    [WARN] Diagram image file not found: {img_path_str}")
                    diagram_image_path = None
            
            # Priority 2: Mermaid code rendering (fallback)
            elif mermaid_code:
                try:
                    from app.services.diagram_service import DiagramService
                    
                    # Generate temporary path
                    timestamp = int(datetime.now().timestamp())
                    temp_img_path = str(Path(output_path).parent / "temp_images" / f"q_{q_no}_{timestamp}.png")
                    
                    print(f"    [INFO] Rendering Mermaid diagram for {q_no}...")
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
                        raise Exception("Mermaid rendering failed")
                        
                except Exception as e:
                    print(f"    ⚠️ Mermaid diagram rendering failed: {e}. Using placeholder.")
                    # Fallback Placeholder
                    pdf.ln(5)
                    pdf.set_fill_color(240, 240, 240)
                    pdf.rect(20, pdf.get_y(), 170, 30, 'FD')
                    pdf.set_xy(25, pdf.get_y()+10)
                    pdf.set_font("helvetica", "I", 10)
                    pdf.multi_cell(160, 5, f"[Diagram Generation Failed: {str(e)[:50]}...]\nMermaid code available in JSON.")
                    pdf.ln(20)
            
            # Priority 3: Text placeholder (if DALL·E and Mermaid both failed or not available)
            elif diagram_placeholder or needs_diagram:
                pdf.ln(5)
                pdf.set_font("helvetica", "I", 10)
                placeholder_text = diagram_placeholder or f"[DIAGRAM PLACEHOLDER: Draw the diagram as described in the question]"
                pdf.multi_cell(0, 5, PDFService._sanitize_text(placeholder_text))
                pdf.ln(3)
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
