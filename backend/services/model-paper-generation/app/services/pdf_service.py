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
        # Remove other special characters that might cause issues
        # Keep basic ASCII and common Unicode
        return text

    @staticmethod
    def _get_available_width(pdf: FPDF) -> float:
        """Calculate available width for text (page width minus margins)."""
        # A4 width is 210mm, get current margins
        left_margin = pdf.l_margin
        right_margin = pdf.r_margin
        return 210 - left_margin - right_margin
    
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
            return False
    
    def _add_question_to_pdf(self, pdf: FPDF, q: Dict[str, Any], q_no: int):
        """Add a single question to the PDF."""
        question_no = q.get("question_no", f"Q{q_no}")
        marks = q.get("marks", 0)
        
        # Question header
        pdf.set_font("helvetica", "B", 12)
        pdf.cell(0, 10, PDFService._sanitize_text(f"{question_no} ({marks} marks)"), ln=True)
        pdf.ln(2)
        
        # Question Stem/Text (if exists and no subquestions, or as intro)
        question_stem = q.get("text", "")
        if question_stem and question_stem.strip():
            # Only show stem if it's substantial and not just a placeholder
            if len(question_stem.strip()) > 20:  # Substantial text
                pdf.set_font("helvetica", "", 11)
                # Use multi_cell for proper text wrapping (handles long lines that exceed page width)
                # Split by newlines first to preserve paragraph structure, then wrap each line if needed
                available_width = PDFService._get_available_width(pdf)
                lines = question_stem.split("\n")
                for line_idx, line in enumerate(lines):
                    sanitized_line = PDFService._sanitize_text(line.strip())
                    if sanitized_line:  # Only process non-empty lines
                        # Use multi_cell with calculated width for automatic wrapping
                        # h=6 is line height, align='L' is left alignment
                        # This ensures long descriptions wrap properly and don't overflow
                        pdf.multi_cell(available_width, 6, sanitized_line, align='L')
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
        text = sq.get("text", "")
        marks = sq.get("marks", 0)
        
        # Handle nested subquestions (e.g., Q4: "a) Write SQL Queries..." with nested i, ii, iii)
        # Or Q3 part (e): "e) [scenario]" with nested i, ii, iii, iv, v
        nested_subquestions = sq.get("subquestions", [])
        
        # Calculate available width for text wrapping
        available_width = PDFService._get_available_width(pdf)
        
        if nested_subquestions:
            # Parent subquestion (bold, e.g., "a) Write SQL Queries to perform the following:")
            pdf.set_font("helvetica", "B", 10)
            if marks:
                # Use multi_cell with calculated width for text wrapping to prevent truncation
                pdf.multi_cell(available_width, 6, PDFService._sanitize_text(f"{label}) {text} ({marks} marks)"), align='L')
            else:
                pdf.multi_cell(available_width, 6, PDFService._sanitize_text(f"{label}) {text}"), align='L')
            pdf.ln(2)
            
            # Nested subquestions (indented, regular font, e.g., "   i. Find...", "   ii. Find...")
            pdf.set_font("helvetica", "", 10)
            for nested_sq in nested_subquestions:
                nested_label = nested_sq.get("label", "")
                nested_text = nested_sq.get("text", "")
                nested_marks = nested_sq.get("marks", 0)

                # CRITICAL: Remove any existing label prefix from nested_text to prevent duplicates (e.g., "i. i. ")
                import re
                # Remove label prefixes (i., ii., iii., iv., v.) at the start of text
                clean_nested_text = nested_text
                while True:
                    old_text = clean_nested_text
                    # Remove label prefixes (with period or space) - remove ALL occurrences
                    clean_nested_text = re.sub(r'^(i{1,3}|iv|v)[\.\s]+\s*', '', clean_nested_text, flags=re.IGNORECASE).strip()
                    if clean_nested_text == old_text:
                        break  # No more labels to remove

                # Format: "   i. Text (marks)" - indented with 3 spaces to show hierarchy
                # Use multi_cell with calculated width for text wrapping to prevent truncation
                if nested_marks:
                    pdf.multi_cell(available_width, 6, PDFService._sanitize_text(f"   {nested_label}. {clean_nested_text} ({nested_marks} marks)"), align='L')
                else:
                    pdf.multi_cell(available_width, 6, PDFService._sanitize_text(f"   {nested_label}. {clean_nested_text}"), align='L')
        else:
            # Regular subquestion (no nesting)
            pdf.set_font("helvetica", "", 10)
            # Use multi_cell with calculated width for text wrapping to prevent truncation
            if marks:
                pdf.multi_cell(available_width, 6, PDFService._sanitize_text(f"{label}) {text} ({marks} marks)"), align='L')
            else:
                pdf.multi_cell(available_width, 6, PDFService._sanitize_text(f"{label}) {text}"), align='L')
        
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
