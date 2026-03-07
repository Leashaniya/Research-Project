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
    
    # Max chars per line for PDF (conservative so downloaded PDF never overflows; frontend is fine)
    _CHARS_PER_LINE = 52

    @staticmethod
    def _wrap_to_lines(text: str, max_chars: int = None) -> list:
        """Split text into lines of at most max_chars (break at spaces). Uses _wrap_long_words first so long/unbreakable words don't break layout."""
        if max_chars is None:
            max_chars = PDFService._CHARS_PER_LINE
        if not text or max_chars <= 0:
            return [text] if text else []
        # Break long words first so line wrapping doesn't get alignment issues
        text = PDFService._wrap_long_words(text, max_chars=max_chars - 2)
        lines = []
        for para in text.split("\n"):
            para = para.strip()
            if not para:
                continue
            while para:
                if len(para) <= max_chars:
                    lines.append(para)
                    break
                idx = para.rfind(" ", 0, max_chars + 1)
                if idx <= 0:
                    idx = min(max_chars, len(para))
                lines.append(para[:idx].strip())
                para = para[idx:].strip()
        return lines

    @staticmethod
    def _wrap_long_words(text: str, max_chars: int = 45) -> str:
        """Break very long words so FPDF can wrap (used together with _wrap_to_lines for safety)."""
        if not text or max_chars <= 0:
            return text
        out = []
        for word in text.split():
            if len(word) > max_chars:
                for i in range(0, len(word), max_chars):
                    out.append(word[i : i + max_chars])
            else:
                out.append(word)
        return " ".join(out)

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Replace characters FPDF cannot handle so document appearance is consistent and text flow is preserved."""
        # Replace problematic characters (substitutions keep meaning and flow; no broken layout)
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

    # A4 and margins (mm) - used for page-break and image checks
    _PAGE_HEIGHT_MM = 297
    _BOTTOM_MARGIN_MM = 18

    @staticmethod
    def _get_available_width(pdf: FPDF) -> float:
        """Content width so text never overflows (frontend shows fine; PDF must stay inside page)."""
        try:
            page_width = getattr(pdf, "w", 210)
        except Exception:
            page_width = 210
        left_margin = pdf.l_margin
        right_margin = pdf.r_margin
        safety = 10.0  # mm
        return max(0, page_width - left_margin - right_margin - safety)

    @staticmethod
    def _get_available_height(pdf: FPDF) -> float:
        """Remaining vertical space (mm) before bottom margin. Use before adding images or large blocks."""
        try:
            page_h = getattr(pdf, "h", PDFService._PAGE_HEIGHT_MM)
        except Exception:
            page_h = PDFService._PAGE_HEIGHT_MM
        current_y = pdf.get_y()
        return max(0, page_h - current_y - PDFService._BOTTOM_MARGIN_MM)
    
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
            # Margins: avoid overflow and keep content clear of footer
            pdf.set_margins(left=22, top=15, right=22)
            pdf.set_auto_page_break(auto=True, margin=PDFService._BOTTOM_MARGIN_MM)
            pdf.add_page()
            
            # Header
            pdf.set_font("helvetica", "B", 18)
            pdf.cell(0, 12, PDFService._sanitize_text("Model Paper - Database Management Systems"), ln=True, align="C")
            pdf.ln(5)
            
            # Metadata
            pdf.set_font("helvetica", "", 11)
            generated_at = paper_data.get("generated_at", "N/A")
            pdf.cell(0, 6, PDFService._sanitize_text(f"Generated: {generated_at}"), ln=True, align="C")
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
        pdf.set_font("helvetica", "B", 13)
        pdf.cell(0, 11, PDFService._sanitize_text(f"{question_no} ({marks} marks)"), ln=True)
        pdf.ln(2)
        
        # Question Stem/Text (if exists and no subquestions, or as intro)
        question_stem = q.get("text", "")
        if question_stem and question_stem.strip():
            # Only show stem if it's substantial and not just a placeholder
            if len(question_stem.strip()) > 20:  # Substantial text
                pdf.set_font("helvetica", "", 12)
                # Use multi_cell for proper text wrapping (handles long lines that exceed page width)
                # Split by newlines first to preserve paragraph structure, then wrap each line if needed
                available_width = PDFService._get_available_width(pdf)
                sanitized = PDFService._sanitize_text(question_stem)
                # Pre-wrap by char count so downloaded PDF never overflows (frontend is already correct)
                for line in PDFService._wrap_to_lines(sanitized):
                    if line:
                        pdf.multi_cell(available_width, 7, line, align='L')
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
                    # Page break: ensure enough space so diagram doesn't push content wrong
                    available_height = PDFService._get_available_height(pdf)
                    if available_height < 50:
                        pdf.add_page()
                        available_height = PDFService._get_available_height(pdf)
                    
                    pdf.ln(3)
                    pdf.set_font("helvetica", "B", 11)
                    diagram_type = q.get("diagram_type", "Diagram")
                    pdf.cell(0, 11, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                    
                    avail_width = PDFService._get_available_width(pdf)
                    # Image scaling: fit within available width and height (with buffer)
                    if Image is not None:
                        try:
                            img = Image.open(img_path_str)
                            img_width, img_height = img.size
                            aspect_ratio = img_height / img_width if img_width > 0 else 1
                            calculated_height_mm = avail_width * aspect_ratio
                            max_height = available_height - 20  # Reserve 20mm buffer
                            if calculated_height_mm > max_height:
                                avail_width = max_height / aspect_ratio
                            avail_width = min(avail_width, PDFService._get_available_width(pdf))
                        except Exception as img_error:
                            print(f"    [WARN] Could not read image dimensions: {img_error}, using default width")
                    
                    pdf.image(img_path_normalized, w=avail_width)
                    pdf.ln(5)
                    print(f"    [OK] Embedded diagram image after question text: {img_path_normalized}")
                except Exception as e:
                    print(f"    [WARN] Failed to embed diagram image: {e}")
                    import traceback
                    traceback.print_exc()
        
        # Subquestions (distinct blocks with spacing between them)
        subquestions = q.get("subquestions", [])
        if subquestions:
            pdf.set_font("helvetica", "", 11)
            for sq_idx, sq in enumerate(subquestions):
                if sq_idx > 0:
                    pdf.ln(5)  # Separation between subquestion blocks
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
        
        def _render_cell(s: str) -> None:
            safe = PDFService._sanitize_text(s)
            # Pre-wrap by char count so downloaded PDF stays inside page
            for line in PDFService._wrap_to_lines(safe):
                if line:
                    pdf.multi_cell(available_width, 7, line, align='L')

        if nested_subquestions:
            # Parent subquestion (bold, e.g., "a) Write SQL Queries to perform the following:")
            pdf.set_font("helvetica", "B", 11)
            if marks:
                _render_cell(f"{label}) {text} ({marks} marks)")
            else:
                _render_cell(f"{label}) {text}")
            pdf.ln(2)
            
            # Nested subquestions (indented, regular font, e.g., "   i. Find...", "   ii. Find...")
            pdf.set_font("helvetica", "", 11)
            for nested_sq in nested_subquestions:
                nested_label = nested_sq.get("label", "")
                nested_text = nested_sq.get("text", "")
                nested_marks = nested_sq.get("marks", 0)

                # CRITICAL: Remove any existing label prefix from nested_text to prevent duplicates (e.g., "i. i. ")
                import re
                clean_nested_text = nested_text
                while True:
                    old_text = clean_nested_text
                    clean_nested_text = re.sub(r'^(i{1,3}|iv|v)[\.\s]+\s*', '', clean_nested_text, flags=re.IGNORECASE).strip()
                    if clean_nested_text == old_text:
                        break

                if nested_marks:
                    _render_cell(f"   {nested_label}. {clean_nested_text} ({nested_marks} marks)")
                else:
                    _render_cell(f"   {nested_label}. {clean_nested_text}")
            pdf.ln(3)  # Extra separation after nested list before diagram/placeholder
        else:
            # Regular subquestion (no nesting)
            pdf.set_font("helvetica", "", 11)
            if marks:
                _render_cell(f"{label}) {text} ({marks} marks)")
            else:
                _render_cell(f"{label}) {text}")
        
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
                    # Page break: ensure enough space for image
                    available_height = PDFService._get_available_height(pdf)
                    if available_height < 50:
                        pdf.add_page()
                        available_height = PDFService._get_available_height(pdf)
                    pdf.ln(5)
                    pdf.set_font("helvetica", "B", 11)
                    diagram_type = parent_q.get("diagram_type", "Diagram")
                    pdf.cell(0, 11, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                    
                    avail_width = PDFService._get_available_width(pdf)
                    # Image scaling: fit within available width and height
                    if Image is not None:
                        try:
                            img = Image.open(img_path_str)
                            iw, ih = img.size
                            ar = ih / iw if iw > 0 else 1
                            calc_h = avail_width * ar
                            max_h = available_height - 20
                            if calc_h > max_h:
                                avail_width = max_h / ar
                            avail_width = min(avail_width, PDFService._get_available_width(pdf))
                        except Exception:
                            pass
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
                        available_height = PDFService._get_available_height(pdf)
                        if available_height < 50:
                            pdf.add_page()
                            available_height = PDFService._get_available_height(pdf)
                        pdf.ln(5)
                        pdf.set_font("helvetica", "B", 11)
                        diagram_type = parent_q.get("diagram_type", "Diagram")
                        pdf.cell(0, 11, PDFService._sanitize_text(f"Figure: {diagram_type}"), ln=True)
                        temp_img_normalized = temp_img_path.replace("\\", "/")
                        avail_w = PDFService._get_available_width(pdf)
                        if Image and os.path.exists(temp_img_path):
                            try:
                                img = Image.open(temp_img_path)
                                iw, ih = img.size
                                ar = ih / iw if iw > 0 else 1
                                if (avail_w * ar) > (available_height - 20):
                                    avail_w = (available_height - 20) / ar
                                avail_w = min(avail_w, PDFService._get_available_width(pdf))
                            except Exception:
                                pass
                        pdf.image(temp_img_normalized, w=avail_w)
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
                    pdf.set_font("helvetica", "I", 10)
                    pdf.cell(0, 6, PDFService._sanitize_text("[DIAGRAM PLACEHOLDER]"), ln=True)
            
        # Priority 3: Placeholder text (pre-wrap so downloaded PDF stays inside page)
        if diagram_placeholder:
            pdf.ln(3)
            pdf.set_font("helvetica", "I", 10)
            available_width = PDFService._get_available_width(pdf)
            ph_safe = PDFService._sanitize_text(diagram_placeholder)
            for line in PDFService._wrap_to_lines(ph_safe):
                if line:
                    pdf.multi_cell(available_width, 6, line, align="L")
