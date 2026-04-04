from fpdf import FPDF
from pathlib import Path
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
try:
    from PIL import Image
except ImportError:
    Image = None  # PIL not available, will skip dimension checking


class PDFService:
    """Service for generating PDF documents from question data."""
    
    def __init__(self):
        self.pdf = None
    
    @staticmethod
    def _strip_duplicate_label_from_text(text: str, label: str) -> str:
        """If text starts with 'label) ' (e.g. 'b) '), strip it to avoid 'b)b)' in PDF."""
        if not text or not label:
            return text
        t = text.strip()
        # Match "a) ", "b) ", "c) " etc. at start (label can be single letter or i, ii, iii)
        prefix = f"{label}) "
        if t.lower().startswith(prefix.lower()):
            return t[len(prefix):].strip()
        return text

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Remove or replace characters that FPDF cannot handle."""
        # Replace problematic characters
        text = text.replace("→", "->")
        text = text.replace("←", "<-")
        text = text.replace("×", "x")
        text = text.replace("÷", "/")
        text = text.replace("±", "+/-")
        # Normalize smart quotes/apostrophes that are not representable in latin-1
        text = text.replace("’", "'")
        text = text.replace("‘", "'")
        text = text.replace("“", '"')
        text = text.replace("”", '"')
        # Normalize dashes and other punctuation that are outside latin-1
        text = text.replace("–", "-")  # en dash
        text = text.replace("—", "-")  # em dash
        text = text.replace("…", "...")  # ellipsis
        # Fallback: ensure string is encodable for FPDF core fonts (latin-1)
        # Characters outside latin-1 can cause truncation or render failures
        try:
            text.encode("latin-1")
        except UnicodeEncodeError:
            text = "".join(c if ord(c) < 256 else "?" for c in text)
        return text

    @staticmethod
    def _get_available_width(pdf: FPDF) -> float:
        """Calculate available width for text (page width minus margins)."""
        # A4 width is 210mm, get current margins
        left_margin = pdf.l_margin
        right_margin = pdf.r_margin
        return 210 - left_margin - right_margin

    @staticmethod
    def _get_available_height(pdf: FPDF, bottom_margin_mm: float = 20) -> float:
        """Approximate available height from current Y to bottom of page (A4 height 297mm)."""
        return 297 - pdf.get_y() - bottom_margin_mm

    @staticmethod
    def _ensure_height_then_ln(pdf: FPDF, need_mm: float = 45) -> None:
        """If remaining height is less than need_mm, add a new page."""
        if PDFService._get_available_height(pdf) < need_mm:
            pdf.add_page()
        pdf.ln(2)
    
    def generate_pdf(self, paper_data: Dict[str, Any], output_path) -> bool:
        """
        Generate a PDF from paper data.
        
        Args:
            paper_data: Dictionary containing paper metadata and questions
            output_path: Path where PDF should be saved
        
        Returns:
            True if successful, False otherwise
        """
        try:
            pdf = FPDF()
            # Set explicit margins to ensure proper text wrapping
            pdf.set_margins(left=15, top=15, right=15)
            pdf.set_auto_page_break(auto=True, margin=15)
            pdf.add_page()
            
            # Header
            pdf.set_font("helvetica", "B", 16)
            pdf.cell(0, 10, PDFService._sanitize_text("Model Paper - Database Management Systems"), ln=True, align="C")
            pdf.ln(5)
            
            # Metadata
            pdf.set_font("helvetica", "", 10)
            generated_at = paper_data.get("generated_at", "N/A")
            pdf.cell(0, 5, PDFService._sanitize_text(f"Generated: {generated_at}"), ln=True, align="C")
            pdf.ln(10)
            
            # Questions
            questions = paper_data.get("questions", [])
            for q_idx, q in enumerate(questions):
                self._add_question_to_pdf(pdf, q, q_idx + 1)
            
            # Save PDF
            output_path_obj = Path(output_path) if isinstance(output_path, str) else output_path
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            pdf.output(str(output_path_obj))
            print(f"PDF successfully exported to: {output_path}")
            return True
            
        except Exception as e:
            print(f"Error generating PDF: {e}")
            import traceback
            traceback.print_exc()
            raise  # re-raise so API can return meaningful 500 detail
    
    def _add_question_to_pdf(self, pdf: FPDF, q: Dict[str, Any], q_no: int):
        """Add a single question to the PDF."""
        question_no = q.get("question_no", f"Q{q_no}")
        marks = q.get("marks")
        
        # Question header (omit "(N marks)" when marks not present — Paper B questions_only)
        pdf.set_font("helvetica", "B", 12)
        if marks is not None and int(marks) > 0:
            header = f"{question_no} ({marks} marks)"
        else:
            header = str(question_no)
        pdf.cell(0, 10, PDFService._sanitize_text(header), ln=True)
        pdf.ln(2)
        
        # Question Stem/Text (if exists and no subquestions, or as intro)
        question_stem = q.get("text", "")
        if question_stem and question_stem.strip():
            # Only show stem if it's substantial and not just a placeholder
            if len(question_stem.strip()) > 20:  # Substantial text
                pdf.set_font("helvetica", "", 11)
                # Use multi_cell for proper text wrapping (handles long lines that exceed page width)
                # Split by newlines first to preserve paragraph structure, then wrap each line if needed
                lines = question_stem.split("\n")
                for line_idx, line in enumerate(lines):
                    sanitized_line = PDFService._sanitize_text(line.strip())
                    if sanitized_line:  # Only process non-empty lines
                        pdf.set_x(pdf.l_margin)  # ensure horizontal space for multi_cell(0,...)
                        pdf.multi_cell(0, 6, sanitized_line, align='L')
                        # Add spacing between paragraphs (but not after the last line)
                        if line_idx < len(lines) - 1:
                            pdf.ln(1)
                pdf.ln(2)
        
        # Check if diagram should be shown after question text (before subquestions)
        diagram_image_path = q.get("diagram_image_path")
        diagram_generated = q.get("diagram_generated", False)
        
        if diagram_generated and diagram_image_path:
            # Convert to string and normalize path for FPDF (use forward slashes)
            img_path_str = str(diagram_image_path) if isinstance(diagram_image_path, Path) else diagram_image_path
            # Normalize path separators for FPDF (works on both Windows and Unix)
            img_path_normalized = img_path_str.replace("\\", "/")
            
            if os.path.exists(img_path_str):
                try:
                    # Check if we need a new page for the diagram
                    # Get current Y position
                    current_y = pdf.get_y()
                    # A4 height is 297mm, bottom margin is 15mm, so available height is 297 - 15 = 282mm
                    # Reserve at least 50mm for the diagram (with some buffer)
                    available_height = 297 - current_y - 15  # 15mm bottom margin
                    
                    # If less than 50mm available, start a new page
                    if available_height < 50:
                        pdf.add_page()
                        current_y = pdf.get_y()
                        available_height = 297 - current_y - 15
                    
                    pdf.ln(3)
                    pdf.set_font("helvetica", "B", 10)
                    diagram_type = q.get("diagram_type", "Diagram")
                    pdf.cell(0, 10, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                    
                    # Calculate available width (A4 width - margins)
                    avail_width = 180
                    
                    # Get image dimensions to check if it fits
                    if Image is not None:
                        try:
                            img = Image.open(img_path_str)
                            img_width, img_height = img.size
                            # Calculate aspect ratio
                            aspect_ratio = img_height / img_width if img_width > 0 else 1
                            # Calculate height in mm (assuming 96 DPI, 1 inch = 25.4mm)
                            # FPDF uses mm, so we need to convert
                            # If width is 180mm, height will be 180mm * aspect_ratio
                            calculated_height_mm = avail_width * aspect_ratio
                            
                            # If diagram is too tall, reduce width proportionally to fit on page
                            max_height = available_height - 20  # Reserve 20mm buffer
                            if calculated_height_mm > max_height:
                                # Reduce width to fit height
                                avail_width = max_height / aspect_ratio
                                # Ensure minimum readable width (at least 120mm)
                                if avail_width < 120:
                                    avail_width = 120
                                    # If still too tall, we'll let it overflow and add page break
                                    if (avail_width * aspect_ratio) > max_height:
                                        # Force page break before diagram
                                        pdf.add_page()
                        except Exception as img_error:
                            # If image reading fails, use default width
                            print(f"    [WARN] Could not read image dimensions: {img_error}, using default width")
                    
                    # Embed diagram image (FPDF.image accepts string path with forward slashes)
                    pdf.image(img_path_normalized, w=avail_width)
                    pdf.ln(5)
                    pdf.set_x(pdf.l_margin)  # reset x so next multi_cell(0,...) has horizontal space
                    print(f"    [OK] Embedded diagram image after question text: {img_path_normalized}")
                except Exception as e:
                    print(f"    [WARN] Failed to embed diagram image: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Subquestions
        subquestions = q.get("subquestions", [])
        if subquestions:
            pdf.set_font("helvetica", "", 10)
            for sq in subquestions:
                self._add_subquestion_to_pdf(pdf, sq, q)
        
        pdf.ln(5)
    
    def _render_subquestion_content(
        self, pdf: FPDF, sq: Dict[str, Any], label: str, text: str, marks: int, available_width: float
    ) -> None:
        """
        Render a single subquestion line or code+question. For Q3(b)-style content with ``` code blocks,
        render code in monospace first, then the question on the next line.
        """
        # Check for markdown-style code block (```...```)
        if "```" in text:
            parts = text.split("```")
            # parts[0] = intro (e.g. "Code Segment: "), parts[1] = code, parts[2] = question text
            pdf.set_font("helvetica", "", 10)
            intro = parts[0].strip()  # e.g. "Code Segment:"
            if intro:
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(0, 6, PDFService._sanitize_text(f"{label}) {intro}"), align='L')
                pdf.ln(2)
            # Code in monospace, line by line for proper alignment
            if len(parts) >= 2:
                code_block = parts[1].strip()
                # Drop leading language tag line like "sql" / "java" / "python"
                code_lines = code_block.split("\n")
                if code_lines and code_lines[0].strip().lower() in {
                    "sql",
                    "java",
                    "python",
                    "js",
                    "javascript",
                    "ts",
                    "typescript",
                }:
                    code_lines = code_lines[1:]
                # Backward compatibility: handle legacy "sql " prefix style
                if code_lines and code_lines[0].strip().lower().startswith("sql "):
                    code_lines[0] = code_lines[0].strip()[4:].strip()
                pdf.set_font("courier", "", 9)
                for line in code_lines:
                    pdf.set_x(pdf.l_margin)  # ensure horizontal space for multi_cell(0,...)
                    if line.strip():
                        pdf.multi_cell(0, 5, PDFService._sanitize_text(line), align='L')
                    else:
                        pdf.ln(3)  # preserve blank lines inside code blocks
                pdf.ln(2)
            # Question on the next line (normal font)
            if len(parts) >= 3:
                question_text = parts[2].strip()
                pdf.set_font("helvetica", "", 10)
                pdf.set_x(pdf.l_margin)
                if marks:
                    pdf.multi_cell(0, 6, PDFService._sanitize_text(f"{question_text} ({marks} marks)"), align='L')
                else:
                    pdf.multi_cell(0, 6, PDFService._sanitize_text(question_text), align='L')
            return
        # No code block: render as single line
        pdf.set_font("helvetica", "", 10)
        pdf.set_x(pdf.l_margin)
        if marks:
            pdf.multi_cell(0, 6, PDFService._sanitize_text(f"{label}) {text} ({marks} marks)"), align='L')
        else:
            pdf.multi_cell(0, 6, PDFService._sanitize_text(f"{label}) {text}"), align='L')

    def _add_subquestion_to_pdf(self, pdf: FPDF, sq: Dict[str, Any], parent_q: Dict[str, Any]):
        """
        Add a subquestion to the PDF, handling nested subquestions.
        
        Supports nested patterns:
        - Q4 part (a): "a) Write SQL Queries to perform the following:" with nested i, ii, iii
        - Q3 part (e): "e) [scenario]" with nested i, ii, iii, iv, v
        
        Format matches past paper structure:
        - Parent subquestion: "a) Parent text" (bold)
        - Nested subquestions: "   i. Nested text (marks)" (indented, regular font)
        """
        label = sq.get("label", "")
        text = str(sq.get("text") or "").strip()
        # Avoid duplicate labels: if text already starts with "b) " etc., strip it so we don't get "b)b)"
        text = PDFService._strip_duplicate_label_from_text(text, label)
        # Be defensive against malformed inputs like ") Some text" which would render "c) ) Some text"
        if text.startswith(") "):
            text = text[2:].lstrip()
        marks = sq.get("marks", 0)
        
        # Handle nested subquestions (e.g., Q4: "a) Write SQL Queries..." with nested i, ii, iii)
        # Or Q3 part (e): "e) [scenario]" with nested i, ii, iii, iv, v
        nested_subquestions = sq.get("subquestions", [])
        
        # Calculate available width for text wrapping
        available_width = PDFService._get_available_width(pdf)
        
        if nested_subquestions:
            # Parent subquestion (bold, e.g., "a) Write SQL Queries to perform the following:")
            pdf.set_font("helvetica", "B", 10)
            pdf.set_x(pdf.l_margin)
            if marks:
                pdf.multi_cell(0, 6, PDFService._sanitize_text(f"{label}) {text} ({marks} marks)"), align='L')
            else:
                pdf.multi_cell(0, 6, PDFService._sanitize_text(f"{label}) {text}"), align='L')
            PDFService._ensure_height_then_ln(pdf, need_mm=45)
            
            # Nested subquestions (indented, regular font, e.g., "   i. Find...", "   ii. Find...")
            pdf.set_font("helvetica", "", 10)
            for nested_sq in nested_subquestions:
                if PDFService._get_available_height(pdf) < 30:
                    pdf.add_page()
                nested_label = nested_sq.get("label", "")
                nested_text = str(nested_sq.get("text") or "").strip()
                nested_marks = nested_sq.get("marks", 0)

                # Remove label prefix from nested_text to prevent "i. i. " (e.g. "i. ", "ii. ")
                clean_nested_text = re.sub(r'^(i{1,3}|iv|v)[\.\s]+\s*', '', nested_text, flags=re.IGNORECASE).strip()
                if not clean_nested_text:
                    clean_nested_text = nested_text

                # Format: "   i. Text (marks)" - indented, full width to right margin
                pdf.set_x(pdf.l_margin)
                if nested_marks:
                    pdf.multi_cell(0, 6, PDFService._sanitize_text(f"   {nested_label}. {clean_nested_text} ({nested_marks} marks)"), align='L')
                else:
                    pdf.multi_cell(0, 6, PDFService._sanitize_text(f"   {nested_label}. {clean_nested_text}"), align='L')
        else:
            # Regular subquestion (no nesting) — may contain code block (e.g. Q3 b)
            self._render_subquestion_content(pdf, sq, label, text, marks, available_width)
        
        pdf.ln(2)
        
        # Check for diagram in subquestion (for code segments, etc.)
        diagram_image_path = sq.get("diagram_image_path")
        diagram_generated = sq.get("diagram_generated", False)
        mermaid_code = sq.get("mermaid_code")
        diagram_placeholder = sq.get("diagram_placeholder")
        
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
                    diagram_type = parent_q.get("diagram_type", "Diagram")
                    pdf.cell(0, 10, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                    
                    # Calculate available width (A4 width - margins)
                    avail_width = 180
                    # Embed diagram image (FPDF.image accepts string path with forward slashes)
                    pdf.image(img_path_normalized, w=avail_width)
                    pdf.ln(5)
                    pdf.set_x(pdf.l_margin)  # reset x so next multi_cell(0,...) has horizontal space
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
            if mermaid_code:
                try:
                    from app.services.diagram_service import DiagramService
                    
                    # Generate temporary path
                    timestamp = int(datetime.now().timestamp())
                    # Use parent question number for temp file naming
                    parent_q_no = parent_q.get("question_no", "Q1")
                    temp_img_path = str(Path("data/outputs/model_papers").parent / "temp_images" / f"{parent_q_no}_{timestamp}.png")
                    Path(temp_img_path).parent.mkdir(parents=True, exist_ok=True)
                    
                    # Render Mermaid to image
                    diagram_service = DiagramService()
                    success = diagram_service.render_mermaid_to_image(mermaid_code, Path(temp_img_path))
                    
                    if success and os.path.exists(temp_img_path):
                        pdf.ln(5)
                        pdf.set_font("helvetica", "B", 10)
                        diagram_type = parent_q.get("diagram_type", "Diagram")
                        pdf.cell(0, 10, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                        
                        # Normalize path
                        temp_img_normalized = temp_img_path.replace("\\", "/")
                        pdf.image(temp_img_normalized, w=180)
                        pdf.ln(5)
                        pdf.set_x(pdf.l_margin)  # reset x so next multi_cell(0,...) has horizontal space
                        
                        # Clean up temp file
                        try:
                            os.remove(temp_img_path)
                        except:
                            pass
                except Exception as e:
                    print(f"    ⚠️ Mermaid diagram rendering failed: {e}. Using placeholder.")
                    # Fallback Placeholder
                    pdf.ln(5)
                    pdf.set_font("helvetica", "I", 9)
                    pdf.cell(0, 5, PDFService._sanitize_text("[DIAGRAM PLACEHOLDER]"), ln=True)
            
        # Priority 3: Placeholder text
        if diagram_placeholder:
            pdf.ln(3)
            pdf.set_font("helvetica", "I", 9)
            pdf.cell(0, 5, PDFService._sanitize_text(diagram_placeholder), ln=True)