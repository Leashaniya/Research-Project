import json
from app.core.config import settings
from app.core.llm_factory import get_llm_client
import re
from app.agents.base import BaseAgent

class QuestionWriter(BaseAgent):
    """
    The Question Writer Agent (Setter).
    Role: Draft questions based on blueprint specs + slide context.
    Using OpenAI GPT-4o-mini.
    """

    def __init__(self, config=None):
        super().__init__(name="Question Writer", config=config)
        self.api_key = settings.OPENAI_API_KEY
        # Always use OpenAI (Azure is not used)
        self.model_name = settings.OPENAI_MODEL or "gpt-4o-mini"
        provider_name = "openai"
        
        try:
            self.client = get_llm_client()
            self.log(f"Initialized LLM ({provider_name}): {self.model_name}")
        except Exception as e:
            self.log(f"Failed to initialize LLM: {e}")
            self.client = None

    async def run(self, input_data: dict) -> dict:
        """
        Input: {
            "slot": {...},
            "template": {...},
            "context": "...",
            "feedback": "...",
            "mode": "generate" | "paraphrase"
        }
        """
        if not self.client:
             raise EnvironmentError("LLM Client not initialized for Writer Agent.")

        slot = input_data["slot"]
        template = input_data["template"]
        context = input_data["context"]
        feedback = input_data.get("feedback")
        mode = input_data.get("mode", "generate") # Default to Generation Mode

        global_context = input_data.get("global_context", {})
        banned_topics = input_data.get("banned_topics", []) or global_context.get("banned_topics", []) or []
        
        # Extract diagram flags from input_data
        needs_diagram = input_data.get("needs_diagram", False)
        diagram_type = input_data.get("diagram_type", None)
        
        # Select Prompt Strategy
        if mode == "generate":
            prompt = self._build_generation_prompt(slot, template, context, global_context, feedback, banned_topics=banned_topics)
            self.log(f"Drafting question for {slot.get('question_no')} (Mode: GEN-FROM-SCRATCH)...")
        else:
            prompt = self._build_paraphrase_prompt(slot, template, context, global_context, feedback, banned_topics=banned_topics)
            self.log(f"Drafting question for {slot.get('question_no')} (Mode: TEMPLATE-PARAPHRASE)...")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
            # --- ENFORCE STRUCTURE COUNT AND NORMALIZE MARKS ---
            # CRITICAL: Ensure subquestion count matches template exactly
            target_marks = slot.get("target_marks", 0)
            required_structure = template.get("required_structure") or []
            required_count = len(required_structure) if required_structure else 0
            
            if target_marks > 0 and parsed.get("subquestions"):
                generated_subquestions = parsed["subquestions"]
                generated_count = len(generated_subquestions)
                
                # Fix count if it doesn't match template
                if required_count > 0 and generated_count != required_count:
                    print(f"    ⚠️  Structure count mismatch: Generated {generated_count}, required {required_count}. Fixing...")
                    generated_subquestions = self._fix_subquestion_count(
                        generated_subquestions,
                        required_structure,
                        required_count,
                        target_marks,
                        template
                    )
                    parsed["subquestions"] = generated_subquestions
                
                # ENFORCE INSTRUCTION PATTERNS: Check if LLM deviated from template patterns
                if required_structure and len(required_structure) > 0:
                    q_no = slot.get("question_no", "")
                    parsed["subquestions"] = self._enforce_instruction_patterns(
                        parsed["subquestions"],
                        required_structure,
                        template,
                        q_no
                    )
                
                # Handle nested subquestions structure (e.g., Q4: "a) Write SQL Queries..." with nested i, ii, iii)
                parsed["subquestions"] = self._restructure_nested_subquestions(
                    parsed["subquestions"],
                    required_structure,
                    template
                )
                
                # Normalize marks to ensure they sum correctly
                # BUT: Preserve exact marks from template structure for nested subquestions
                # Only normalize if marks don't match or are missing
                parsed["subquestions"] = self._normalize_subquestion_marks(
                    parsed["subquestions"], 
                    target_marks,
                    template  # Pass template to preserve nested marks
                )
                # Update main question marks to match (in case LLM got it wrong)
                parsed["marks"] = target_marks
            # -----------------------------------------------------
            
            # --- DIAGRAM HANDLING (DALL·E Integration) ---
            # Note: DALL·E image generation happens AFTER question approval in orchestrator
            # Here we just ensure the question structure is ready for diagram generation
            if needs_diagram:
                # Store diagram metadata for later DALL·E generation
                parsed["needs_diagram"] = True
                parsed["diagram_type"] = diagram_type
                # Keep Mermaid code as fallback if DALL·E fails
                if not parsed.get("mermaid_code"):
                    print(f"    ⚠️ Writer did not generate Mermaid code. Will use DALL·E or fallback.")
                    parsed["mermaid_code"] = None  # Will be generated by DALL·E or use placeholder
            # ---------------------------

            # Handle code segment references - detect and add code if needed
            parsed = self._handle_code_segment_references(parsed, template, slot)
            
            # Fix subquestion references (e.g., "queries (i) to (iv)" when labels are a, b, c, d)
            parsed = self._fix_subquestion_references(parsed, template)
            
            # CRITICAL: Q3 part (c) scenario placement - scenario should be above part (c), not part (a)
            parsed = self._fix_q3_scenario_placement(parsed, template, slot)
            
            # Validation: Check for empty stem
            if not parsed.get("text") or len(parsed.get("text", "").strip()) < 20:
                raise ValueError("Generated empty or too-short question stem (text field)")
            
            # Validation: Check for empty subquestion text
            for sq in parsed.get("subquestions", []):
                if not sq.get("text") or len(sq.get("text").strip()) < 5:
                    raise ValueError(f"Generated empty question text for label {sq.get('label')}")
                    
            return parsed
        except Exception as e:
            self.log(f"Error drafting question: {e}")
            raise e

    def _normalize_subquestion_marks(self, subquestions: list, target_marks: int, template: dict = None) -> list:
        """
        Normalize subquestion marks to ensure they sum exactly to target_marks.
        Uses proportional distribution based on relative weightage.
        Handles nested subquestions properly (parent with null marks, nested items with marks).
        
        Args:
            subquestions: List of subquestion dicts with 'marks' field
            target_marks: Target total marks for all subquestions
            template: Optional template dict for nested structure marks
            
        Returns:
            List of subquestions with normalized marks that sum to target_marks
        """
        if not subquestions or target_marks <= 0:
            return subquestions
        
        # CRITICAL: Handle nested subquestions (Q4 part a, Q3 part e)
        # For nested subquestions, parent has null marks and nested items have marks
        # We need to calculate marks including nested items
        def get_effective_marks(sq):
            """Get effective marks for a subquestion (including nested items if present)."""
            sq_marks = sq.get("marks")
            # If marks is None, it's a parent with nested items
            if sq_marks is None:
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # Sum marks from nested items
                    return sum(int(item.get("marks") or 0) for item in nested_items)
            return int(sq_marks or 0)
        
        # Get current marks (including nested items)
        current_marks = [get_effective_marks(sq) for sq in subquestions]
        current_sum = sum(current_marks)
        
        # If sum is already correct, return as-is (but ensure no 0 marks in nested items)
        if current_sum == target_marks:
            # Still check for 0 marks in nested items
            for sq in subquestions:
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    for nested_item in nested_items:
                        if int(nested_item.get("marks") or 0) <= 0:
                            nested_item["marks"] = 1
            return subquestions
        
        # If all marks are 0 or invalid, distribute evenly
        if current_sum == 0 or all(m == 0 for m in current_marks):
            marks_per_subq = target_marks // len(subquestions)
            remainder = target_marks % len(subquestions)
            normalized = []
            for idx, sq in enumerate(subquestions):
                # Check if this subquestion has nested items
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # Distribute marks among nested items
                    nested_marks_per_item = max(1, marks_per_subq // len(nested_items))
                    for nested_item in nested_items:
                        nested_item["marks"] = nested_marks_per_item
                    sq["marks"] = None  # Parent has null marks
                else:
                    marks = marks_per_subq + (1 if idx < remainder else 0)
                    sq["marks"] = marks
                normalized.append(sq)
            return normalized
        
        # Proportional distribution: scale each mark by the ratio
        ratio = target_marks / current_sum if current_sum > 0 else 1
        normalized_marks = [int(round(m * ratio)) for m in current_marks]
        
        # CRITICAL: Ensure no subquestion gets 0 marks (minimum is 1)
        # For nested subquestions, ensure nested items have at least 1 mark each
        for i, sq in enumerate(subquestions):
            nested_items = sq.get("subquestions", [])
            if nested_items:
                # Distribute normalized_marks[i] among nested items
                if normalized_marks[i] <= 0:
                    normalized_marks[i] = len(nested_items)  # At least 1 per nested item
                nested_marks_per_item = max(1, normalized_marks[i] // len(nested_items))
                remainder_nested = normalized_marks[i] % len(nested_items)
                for idx, nested_item in enumerate(nested_items):
                    nested_item["marks"] = nested_marks_per_item + (1 if idx < remainder_nested else 0)
                sq["marks"] = None  # Parent has null marks
            else:
                if normalized_marks[i] <= 0:
                    normalized_marks[i] = 1
                sq["marks"] = normalized_marks[i]
        
        # Update subquestions with normalized marks
        # CRITICAL: Preserve None marks for parents with nested items
        normalized = []
        for idx, sq in enumerate(subquestions):
            nested_items = sq.get("subquestions", [])
            if nested_items:
                # Parent with nested items: marks should be None
                # The marks are already distributed among nested items above
                normalized.append({**sq, "marks": None})
            else:
                # Regular subquestion: use normalized marks
                normalized.append({**sq, "marks": normalized_marks[idx]})
        
        # Fix rounding errors: ensure sum equals target_marks exactly
        # Recalculate sum after creating normalized list
        normalized_sum = sum(get_effective_marks(sq) for sq in normalized)
        diff = target_marks - normalized_sum
        
        if diff != 0:
            # Distribute the difference to the largest subquestions first
            # This preserves the relative weightage better
            # Create a list of (index, effective_marks) for sorting
            sq_with_marks = []
            for idx, sq in enumerate(normalized):
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # For nested, use sum of nested items
                    effective = sum(int(item.get("marks") or 0) for item in nested_items)
                else:
                    effective = int(sq.get("marks") or 0)
                sq_with_marks.append((idx, effective))
            
            sorted_indices = sorted(sq_with_marks, key=lambda x: x[1], reverse=True)
            
            # Add/subtract the difference
            for idx, _ in sorted_indices:
                if diff == 0:
                    break
                sq = normalized[idx]
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # Adjust nested items
                    if diff > 0:
                        # Add to first nested item
                        if nested_items:
                            current = int(nested_items[0].get("marks") or 0)
                            nested_items[0]["marks"] = current + 1
                            diff -= 1
                    else:
                        # Subtract from first nested item (if > 1)
                        if nested_items and int(nested_items[0].get("marks") or 0) > 1:
                            current = int(nested_items[0].get("marks") or 0)
                            nested_items[0]["marks"] = current - 1
                            diff += 1
                else:
                    # Adjust regular subquestion
                    if diff > 0:
                        current = int(sq.get("marks") or 0)
                        sq["marks"] = current + 1
                        diff -= 1
                    else:
                        current = int(sq.get("marks") or 0)
                        if current > 1:
                            sq["marks"] = current - 1
                            diff += 1
        
        # Final verification using get_effective_marks helper
        final_sum = sum(get_effective_marks(sq) for sq in normalized)
        if final_sum != target_marks:
            # Last resort: adjust marks
            # Find the last non-nested subquestion or adjust nested items
            for i in range(len(normalized) - 1, -1, -1):
                sq = normalized[i]
                nested_items = sq.get("subquestions", [])
                if nested_items:
                    # Adjust nested items if needed
                    nested_sum = sum(int(item.get("marks") or 0) for item in nested_items)
                    diff = target_marks - (final_sum - nested_sum)
                    if diff != 0 and nested_items:
                        # Distribute difference among nested items
                        per_item = diff // len(nested_items)
                        remainder = diff % len(nested_items)
                        for j, item in enumerate(nested_items):
                            current = int(item.get("marks") or 0)
                            item["marks"] = max(1, current + per_item + (1 if j < remainder else 0))
                    break
                else:
                    # Adjust regular subquestion
                    current = int(sq.get("marks") or 0)
                    diff = target_marks - final_sum
                    sq["marks"] = max(1, current + diff)
                    break
        
        return normalized

    def _fix_subquestion_count(self, subquestions: list, required_structure: list, required_count: int, target_marks: int, template: dict) -> list:
        """
        Fix subquestion count to match required structure exactly.
        If too few, add new ones. If too many, remove excess.
        
        Args:
            subquestions: Generated subquestions from LLM
            required_structure: Template structure with required parts
            required_count: Exact number of subquestions required
            target_marks: Total marks for the question
            template: Template dict for pattern_label reference
            
        Returns:
            List of subquestions with correct count
        """
        current_count = len(subquestions)
        
        # If count is correct, return as-is
        if current_count == required_count:
            return subquestions
        
        # If too few, add new subquestions
        if current_count < required_count:
            import string
            # Use existing subquestions as base
            fixed = list(subquestions)
            
            # Add missing subquestions based on required structure
            for idx in range(current_count, required_count):
                if idx < len(required_structure):
                    struct_item = required_structure[idx]
                    label = string.ascii_lowercase[idx % 26]
                    marks = struct_item.get("marks", target_marks // required_count)
                    
                    # Generate text based on structure or use generic
                    text = struct_item.get("text", "")
                    if not text or len(text.strip()) < 10:
                        pattern_label = template.get("pattern_label", "the topic")
                        text = f"Complete the task related to {pattern_label}."
                    
                    fixed.append({
                        "label": label,
                        "marks": marks,
                        "text": text
                    })
                else:
                    # Fallback if structure doesn't have enough items
                    label = string.ascii_lowercase[idx % 26]
                    marks = target_marks // required_count
                    pattern_label = template.get("pattern_label", "the topic")
                    fixed.append({
                        "label": label,
                        "marks": marks,
                        "text": f"Complete the task related to {pattern_label}."
                    })
            
            return fixed
        
        # If too many, remove excess (keep first N)
        if current_count > required_count:
            return subquestions[:required_count]
        
        return subquestions

    def _enforce_instruction_patterns(self, subquestions: list, required_structure: list, template: dict = None, q_no: str = None) -> list:
        """
        Enforce instruction patterns from template if LLM deviated.
        For each sub-question, if template has a text pattern, ensure the generated text preserves it.
        Also ensures marks match the template structure exactly.
        """
        if not required_structure or len(required_structure) != len(subquestions):
            return subquestions
        
        pattern_label = template.get('pattern_label', '').lower() if template else ''
        enforced = []
        import string
        for idx, (sq, struct_item) in enumerate(zip(subquestions, required_structure)):
            # Ensure all subquestions have proper labels (a, b, c, d, e, f, g, h, i, ...)
            if not sq.get("label") or sq.get("label") == "?":
                sq["label"] = string.ascii_lowercase[idx % 26]
            template_text = struct_item.get("text", "").strip()
            
            # Get generated text early for Q4 enforcement (even without template pattern)
            generated_text = sq.get("text", "").strip()
            
            # Clean generated text (remove label prefix like "i.", "ii.", "a)", "b)", etc.)
            clean_generated = generated_text
            if clean_generated and len(clean_generated) > 2:
                # First handle "ii.", "iii.", "iv.", etc. (before single char prefixes)
                if clean_generated.lower().startswith(("ii. ", "iii. ", "iv. ", "v. ")):
                    parts = clean_generated.split(". ", 1)
                    if len(parts) > 1:
                        clean_generated = parts[1].strip()
                # Also handle "i. " pattern
                elif clean_generated.lower().startswith("i. "):
                    parts = clean_generated.split(". ", 1)
                    if len(parts) > 1:
                        clean_generated = parts[1].strip()
                # Then handle single char prefixes like "a)", "b)", etc.
                elif len(clean_generated) > 2 and clean_generated[1] in [')', '.', '?']:
                    clean_generated = clean_generated[2:].strip()
            
            # For Q4 first two subquestions, always enforce "Write SQL queries" if they start with "Find"
            is_q4_first_two = ("sql" in pattern_label and idx < 2)
            # More robust check: look for "Find" anywhere near the start (after label prefix)
            text_lower = generated_text.lower().strip()
            # Check multiple patterns to catch "Find" even with prefixes
            has_find_pattern = (
                clean_generated.lower().startswith("find") or 
                text_lower.startswith("find") or
                text_lower.startswith("ii. find") or
                text_lower.startswith("iii. find") or
                text_lower.startswith("iv. find") or
                (len(text_lower) > 4 and text_lower[0:5] == "find ") or
                (len(text_lower) > 7 and "find" in text_lower[4:10]) or  # After "ii. " or "iii. "
                (len(text_lower) > 8 and "find" in text_lower[5:11])     # After "iii. "
            )
            
            if is_q4_first_two and has_find_pattern and not text_lower.startswith("write sql queries") and "create" not in text_lower and "trigger" not in text_lower and "function" not in text_lower:
                # Extract the query part - try multiple methods
                query_part = None
                if "Find" in clean_generated:
                    query_part = clean_generated.split("Find", 1)[1].strip()
                elif "find" in clean_generated.lower():
                    # Find the position of "find" (case-insensitive)
                    find_pos = clean_generated.lower().find("find")
                    if find_pos >= 0:
                        # Get everything after "find"
                        remaining = clean_generated[find_pos + 4:].strip()
                        query_part = remaining
                
                if query_part:
                    # Preserve original label prefix if present
                    label_prefix = ""
                    if generated_text and len(generated_text) > 2 and generated_text[1] in [')', '.']:
                        label_prefix = generated_text[:2] + " "
                    elif generated_text.lower().startswith(("i. ", "ii. ", "iii. ", "iv. ")):
                        parts = generated_text.split(". ", 1)
                        if len(parts) > 1:
                            label_prefix = parts[0] + ". "
                    generated_text = f"{label_prefix}Write SQL queries to find {query_part}"
                    sq["text"] = generated_text
                    # Update clean_generated after modification
                    clean_generated = generated_text
                    if clean_generated and len(clean_generated) > 2:
                        if clean_generated.lower().startswith(("ii. ", "iii. ", "iv. ", "v. ")):
                            parts = clean_generated.split(". ", 1)
                            if len(parts) > 1:
                                clean_generated = parts[1].strip()
                        elif clean_generated.lower().startswith("i. "):
                            parts = clean_generated.split(". ", 1)
                            if len(parts) > 1:
                                clean_generated = parts[1].strip()
                        elif len(clean_generated) > 2 and clean_generated[1] in [')', '.', '?']:
                            clean_generated = clean_generated[2:].strip()
                    self.log(f"    🔧 Enforced SQL query pattern: Converted 'Find' to 'Write SQL queries' for subquestion {sq.get('label', idx)}")
            
            # If template has text pattern, check if we should enforce it
            if template_text and len(template_text) > 10:
                # Clean template text (remove label prefix)
                clean_template = template_text
                if clean_template and len(clean_template) > 2 and clean_template[1] in [')', '.', '?']:
                    clean_template = clean_template[2:].strip()
                
                # For SQL_DDL_DML questions, convert "Find" patterns to "Write SQL queries"
                if "sql" in pattern_label and clean_template.lower().startswith("find"):
                    if "find" in clean_template.lower():
                        query_part = clean_template.split("Find", 1)[1].strip() if "Find" in clean_template else clean_template.split("find", 1)[1].strip()
                        clean_template = f"Write SQL queries to find {query_part}"
                
                # Extract instruction pattern (the task/instruction part, not the scenario)
                # For patterns like "Briefly explain...", "Write a T-SQL statement...", "Accept or refute..."
                # We want to preserve these exact phrases
                # Note: generated_text and clean_generated are already set above for Q4 enforcement
                if "generated_text" not in locals() or "clean_generated" not in locals():
                    generated_text = sq.get("text", "").strip()
                    # Clean generated text (remove label prefix like "i.", "ii.", "a)", "b)", etc.)
                    clean_generated = generated_text
                    if clean_generated and len(clean_generated) > 2:
                        # First handle "ii.", "iii.", "iv.", etc. (before single char prefixes)
                        if clean_generated.lower().startswith(("ii. ", "iii. ", "iv. ", "v. ")):
                            parts = clean_generated.split(". ", 1)
                            if len(parts) > 1:
                                clean_generated = parts[1].strip()
                        # Also handle "i. " pattern
                        elif clean_generated.lower().startswith("i. "):
                            parts = clean_generated.split(". ", 1)
                            if len(parts) > 1:
                                clean_generated = parts[1].strip()
                        # Then handle single char prefixes like "a)", "b)", etc.
                        elif len(clean_generated) > 2 and clean_generated[1] in [')', '.', '?']:
                            clean_generated = clean_generated[2:].strip()
                
                # For SQL questions with "Find" pattern, enforce "Write SQL queries"
                # Check if template pattern was converted to "Write SQL queries" OR if template originally starts with "find"
                template_should_be_sql_query = (
                    clean_template.lower().startswith("write sql queries") or
                    ("sql" in pattern_label and clean_template.lower().startswith("find"))
                )
                
                # Also check if this is Q4 (SQL_DDL_DML) and first two subquestions (idx 0 and 1)
                is_q4_first_two = ("sql" in pattern_label and idx < 2)
                
                if template_should_be_sql_query or is_q4_first_two:
                    # If generated text doesn't start with "Write SQL queries", convert it
                    if not clean_generated.lower().startswith("write sql queries"):
                        if clean_generated.lower().startswith("find"):
                            # Convert "Find X" to "Write SQL queries to find X"
                            query_part = clean_generated.split("Find", 1)[1].strip() if "Find" in clean_generated else clean_generated.split("find", 1)[1].strip()
                            # Preserve original label prefix if present
                            label_prefix = ""
                            if generated_text and len(generated_text) > 2 and generated_text[1] in [')', '.']:
                                label_prefix = generated_text[:2] + " "
                            elif generated_text.lower().startswith(("i. ", "ii. ", "iii. ", "iv. ")):
                                parts = generated_text.split(". ", 1)
                                if len(parts) > 1:
                                    label_prefix = parts[0] + ". "
                            generated_text = f"{label_prefix}Write SQL queries to find {query_part}"
                            sq["text"] = generated_text
                            self.log(f"    🔧 Enforced SQL query pattern: Converted 'Find' to 'Write SQL queries' for subquestion {sq.get('label', idx)}")
                        elif is_q4_first_two and "create" not in clean_generated.lower() and "trigger" not in clean_generated.lower() and "function" not in clean_generated.lower():
                            # For Q4 first two parts, if it's not already a create statement, ensure it says "Write SQL queries"
                            if "query" not in clean_generated.lower() and "sql" not in clean_generated.lower():
                                # Preserve label prefix
                                label_prefix = ""
                                if generated_text and len(generated_text) > 2 and generated_text[1] in [')', '.']:
                                    label_prefix = generated_text[:2] + " "
                                elif generated_text.lower().startswith(("i. ", "ii. ", "iii. ", "iv. ")):
                                    parts = generated_text.split(". ", 1)
                                    if len(parts) > 1:
                                        label_prefix = parts[0] + ". "
                                generated_text = f"{label_prefix}Write SQL queries to {clean_generated.lower()}"
                                sq["text"] = generated_text
                                self.log(f"    🔧 Enforced SQL query pattern: Added 'Write SQL queries' prefix for subquestion {sq.get('label', idx)}")
                
                # Check if generated text matches the instruction pattern
                # CRITICAL: "Briefly explain" must be preserved exactly
                needs_enforcement = False
                
                # For Q2 normalization questions, check if template has specific patterns that MUST be enforced
                # Check for "Draw the functional dependency diagram" - this is a critical pattern
                if "draw the functional dependency diagram" in clean_template.lower():
                    if "draw" not in generated_text.lower() or "functional dependency diagram" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 Q2 Pattern Mismatch: Template requires 'Draw the functional dependency diagram' but got: {generated_text[:50]}...")
                
                # Check for detailed 3NF decomposition pattern - this is a critical pattern
                if "design a set of 3nf relations" in clean_template.lower() and "show clearly each stage" in clean_template.lower():
                    if "design a set of 3nf" not in generated_text.lower() or "show clearly each stage" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 Q2 Pattern Mismatch: Template requires detailed 3NF decomposition but got: {generated_text[:50]}...")
                
                # Check for "Briefly explain" - this is CRITICAL
                if "briefly explain" in clean_template.lower():
                    if "briefly explain" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 CRITICAL: Missing 'Briefly' qualifier in sub-question {sq.get('label', idx)} - enforcing template pattern")
                
                # Check for "Accept or refute"
                if "accept or refute" in clean_template.lower():
                    if "accept or refute" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 Enforcing 'Accept or refute' pattern for sub-question {sq.get('label', idx)}")
                
                # CRITICAL: Q3 subquestion (a) must include JDBC Type 2 Driver statement
                # Template pattern: "In Type 2 Driver, JDBC API calls are converted to native Java API calls. Accept or refute..."
                if idx == 0 and "sql" in pattern_label.lower() and "type 2 driver" in clean_template.lower():
                    if "type 2 driver" not in generated_text.lower() and "jdbc" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 CRITICAL: Q3 subquestion (a) missing JDBC Type 2 Driver statement - enforcing template pattern")
                    # Also check if it incorrectly says "Write SQL queries" instead of JDBC statement
                    if "write sql queries" in clean_generated.lower() and "type 2 driver" in clean_template.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 CRITICAL: Q3 subquestion (a) incorrectly uses 'Write SQL queries' instead of JDBC Type 2 Driver - enforcing template pattern")
                
                # CRITICAL: Q1 subquestion (a) must be "Convert the following EER model into the relational model..."
                # Template pattern: "a) Convert the following EER model into the relational model. Indicate the primary keys and the foreign keys of the resulting relations clearly."
                if q_no and q_no in ["Q1", "1"] and idx == 0 and ("er" in pattern_label.lower() or "eer" in pattern_label.lower()):
                    if "convert the following eer model" in clean_template.lower() or "convert the following er model" in clean_template.lower():
                        if "convert" not in generated_text.lower() or "relational model" not in generated_text.lower():
                            needs_enforcement = True
                            self.log(f"    🔧 CRITICAL: Q1 subquestion (a) must be 'Convert the following EER model into the relational model...' - enforcing template pattern")
                
                # CRITICAL: Q4 subquestion (a) must be "Write SQL Queries to perform the following:" with nested i, ii, iii
                # Template pattern: "a) Write SQL Queries to perform the following: i. Find..."
                if q_no and q_no in ["Q4", "4"] and idx == 0 and "sql" in pattern_label.lower():
                    if "write sql queries to perform the following" not in generated_text.lower():
                        # Enforce exact template pattern
                        sq["text"] = "Write SQL Queries to perform the following:"
                        self.log(f"    🔧 CRITICAL: Q4 subquestion (a) enforced to 'Write SQL Queries to perform the following:'")
                
                # CRITICAL: Q4 subquestion (b) must be "Create a function..." not "Create a SQL query..."
                # Template pattern: "b) Create a function to calculate..."
                if q_no and q_no in ["Q4", "4"] and idx == 1 and "sql" in pattern_label.lower():
                    if "create a function" not in generated_text.lower() and "create a sql query" in generated_text.lower():
                        # Replace "Create a SQL query" with "Create a function"
                        # Extract the function purpose from the text
                        function_purpose = ""
                        if "to" in generated_text.lower():
                            to_pos = generated_text.lower().find(" to ")
                            if to_pos > 0:
                                function_purpose = generated_text[to_pos + 4:].strip()
                        else:
                            # Try to extract purpose from context
                            function_purpose = "calculate the total amount"  # Default
                        
                        sq["text"] = f"Create a function to {function_purpose}"
                        self.log(f"    🔧 CRITICAL: Q4 subquestion (b) enforced to 'Create a function...' instead of 'Create a SQL query...'")
                
                # CRITICAL: Q4 subquestion (c) must be "Create a trigger..." not "Create a procedure..." or "Create a SQL command..."
                # Template pattern: "c) Create a trigger that automatically updates..."
                if q_no and q_no in ["Q4", "4"] and idx == 2 and "sql" in pattern_label.lower():
                    if "create a trigger" not in generated_text.lower():
                        # Check if it says something else like "Create a procedure" or "Create a SQL command"
                        if "create a procedure" in generated_text.lower() or "create a sql command" in generated_text.lower() or "create a sql statement" in generated_text.lower():
                            # Extract the trigger purpose from the text
                            trigger_purpose = ""
                            if "that" in generated_text.lower():
                                that_pos = generated_text.lower().find(" that ")
                                if that_pos > 0:
                                    trigger_purpose = generated_text[that_pos + 6:].strip()
                            elif "to" in generated_text.lower():
                                to_pos = generated_text.lower().find(" to ")
                                if to_pos > 0:
                                    trigger_purpose = generated_text[to_pos + 4:].strip()
                            else:
                                # Try to extract purpose from context
                                trigger_purpose = "automatically updates the total amount"  # Default
                            
                            sq["text"] = f"Create a trigger that {trigger_purpose}"
                            self.log(f"    🔧 CRITICAL: Q4 subquestion (c) enforced to 'Create a trigger...' instead of 'Create a procedure/SQL command...'")
                        elif "trigger" not in generated_text.lower():
                            # If trigger is completely missing, enforce it from template
                            if "create a trigger" in clean_template.lower():
                                sq["text"] = template_text
                                self.log(f"    🔧 CRITICAL: Q4 subquestion (c) missing trigger - enforcing template pattern")
                
                # CRITICAL: Q3 subquestion (b) must NOT include hints that give away the answer
                # Template pattern: "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                # DO NOT include hints like "SQL statements are used to create tables" or "DDL is used to define" - these give away the answer
                if idx == 1 and "sql" in pattern_label.lower() and q_no and q_no in ["Q3", "3"] and ("which" in clean_template.lower() or "code segment" in clean_template.lower()):
                    # Check for hints that give away the answer
                    hint_patterns = [
                        r'sql\s+statements?\s+are\s+used\s+to',
                        r'ddl\s+is\s+used\s+to',
                        r'sql\s+data\s+definition\s+language',
                        r'to\s+create\s+the\s+tables?\s+mentioned',
                        r'these?\s+statements?\s+are\s+used\s+to',
                        r'are\s+used\s+to\s+create\s+the\s+tables?',
                        r'are\s+used\s+to\s+create',
                        r'used\s+to\s+create\s+the\s+tables?\s+mentioned\s+in\s+this\s+scenario',
                        r'used\s+to\s+create\s+the\s+tables?',
                        r'in\s+this\s+scenario.*are\s+used\s+to\s+create'
                    ]
                    has_hints = any(re.search(pattern, generated_text, re.IGNORECASE) for pattern in hint_patterns)
                    
                    if has_hints:
                        # Remove hints and enforce exact template pattern
                        cleaned_text = generated_text
                        for pattern in hint_patterns:
                            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)
                        # Clean up multiple spaces and punctuation
                        cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
                        cleaned_text = re.sub(r'\s*[.,]\s*$', '', cleaned_text)
                        
                        # Enforce exact template: "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                        if "which type" in cleaned_text.lower():
                            # Extract just the question part if it exists
                            which_match = re.search(r'which\s+type[^?]*\?', cleaned_text, re.IGNORECASE)
                            if which_match and "briefly explain" in cleaned_text.lower():
                                # Keep the question but ensure it follows template
                                sq["text"] = "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                            else:
                                sq["text"] = "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                        else:
                            sq["text"] = "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                        
                        self.log(f"    🔧 CRITICAL: Q3 subquestion (b) had hints removed - enforcing template pattern without hints")
                
                # Check for "Write a T-SQL statement"
                if "write a t-sql statement" in clean_template.lower():
                    if "write a t-sql statement" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 Enforcing 'Write a T-SQL statement' pattern for sub-question {sq.get('label', idx)}")
                
                # Check for "Draw the functional dependency diagram" (Q2 pattern)
                if "draw the functional dependency diagram" in clean_template.lower():
                    if "draw the functional dependency diagram" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 Enforcing 'Draw the functional dependency diagram' pattern for sub-question {sq.get('label', idx)}")
                
                # Check for detailed 3NF decomposition instruction (Q2 pattern)
                # Template: "Using the above functional dependencies, design a set of 3NF relations... Show clearly each stage..."
                if "design a set of 3nf relations" in clean_template.lower() or "show clearly each stage in deriving the 3nf relations" in clean_template.lower():
                    if "design a set of 3nf relations" not in generated_text.lower() and "show clearly each stage" not in generated_text.lower():
                        needs_enforcement = True
                        self.log(f"    🔧 Enforcing detailed 3NF decomposition pattern for sub-question {sq.get('label', idx)}")
                
                # For Q2 normalization questions, be more strict about pattern matching
                # If template has specific instruction pattern, enforce it strictly
                pattern_label = struct_item.get("type", "").lower() if isinstance(struct_item, dict) else ""
                is_q2_norm = "draw" in pattern_label or "list" in pattern_label
                
                # Check if this is a critical Q2 pattern that must be enforced
                is_critical_q2_pattern = (
                    "draw the functional dependency diagram" in clean_template.lower() or
                    "design a set of 3nf relations" in clean_template.lower() or
                    "show clearly each stage in deriving" in clean_template.lower()
                )
                
                # CRITICAL: Always enforce marks from template structure
                template_marks = struct_item.get("marks")
                if template_marks is not None and template_marks > 0:
                    sq["marks"] = int(template_marks)
                    current_marks = sq.get("marks")
                    if current_marks is not None and int(current_marks or 0) != int(template_marks):
                        self.log(f"    ✅ Enforced marks from template: {template_marks} for sub-question {sq.get('label', idx)}")
                
                # For short patterns (< 150 chars) OR critical Q2 patterns, use template text directly
                if needs_enforcement and (len(clean_template) < 150 or is_critical_q2_pattern):
                    sq["text"] = clean_template
                    self.log(f"    ✅ Enforced exact template pattern for sub-question {sq.get('label', idx)}")
                # For long patterns (with scenarios), we need to preserve the instruction part
                elif needs_enforcement and len(clean_template) >= 150:
                    # Extract the instruction part (usually the last sentence or phrase)
                    # For T-SQL patterns, the instruction is usually at the end
                    if "write a t-sql statement" in clean_template.lower():
                        # Find the instruction part (from "Write a T-SQL" to end)
                        tsql_start = clean_template.lower().find("write a t-sql statement")
                        if tsql_start >= 0:
                            instruction_part = clean_template[tsql_start:]
                            # Try to merge: keep generated scenario but use template instruction
                            # For now, use template text to ensure correctness
                            sq["text"] = clean_template
                            self.log(f"    ✅ Enforced long scenario pattern for sub-question {sq.get('label', idx)}")
                        else:
                            self.log(f"    ⚠️  Long scenario pattern detected - using full template text")
                            sq["text"] = clean_template
                    elif "design a set of 3nf relations" in clean_template.lower() or "show clearly each stage" in clean_template.lower():
                        # For 3NF decomposition pattern, use template text exactly
                        sq["text"] = clean_template
                        self.log(f"    ✅ Enforced 3NF decomposition pattern for sub-question {sq.get('label', idx)}")
                    else:
                        # For other long patterns, use template text
                        sq["text"] = clean_template
                        self.log(f"    ✅ Enforced template pattern for long scenario sub-question {sq.get('label', idx)}")
            
            # Always ensure marks match template structure (even if text wasn't enforced)
            template_marks = struct_item.get("marks")
            if template_marks is not None and template_marks > 0:
                current_marks = sq.get("marks")
                if current_marks is None or int(current_marks or 0) != int(template_marks):
                    sq["marks"] = int(template_marks)
                    self.log(f"    ✅ Enforced marks from template: {template_marks} for sub-question {sq.get('label', idx)}")
            
            enforced.append(sq)
        
        # Final pass: Ensure Q4 first two subquestions have "Write SQL queries" if they start with "Find"
        if pattern_label and "sql" in pattern_label:
            for idx, sq in enumerate(enforced):
                if idx < 2:  # First two subquestions
                    text = sq.get("text", "").strip()
                    text_lower = text.lower()
                    # Check if it starts with "Find" but not "Write SQL queries"
                    if (text_lower.startswith("find") or 
                        text_lower.startswith("ii. find") or 
                        text_lower.startswith("iii. find") or
                        (len(text_lower) > 4 and text_lower[0:5] == "find ")) and \
                       not text_lower.startswith("write sql queries") and \
                       "create" not in text_lower and "trigger" not in text_lower and "function" not in text_lower:
                        # Extract query part
                        if "find" in text_lower:
                            find_pos = text_lower.find("find")
                            query_part = text[find_pos + 4:].strip()
                            # Preserve label prefix
                            label_prefix = ""
                            if text.lower().startswith(("ii. ", "iii. ", "iv. ")):
                                parts = text.split(". ", 1)
                                if len(parts) > 1:
                                    label_prefix = parts[0] + ". "
                            sq["text"] = f"{label_prefix}Write SQL queries to find {query_part}"
                            self.log(f"    🔧 Final enforcement: Converted 'Find' to 'Write SQL queries' for subquestion {sq.get('label', idx)}")
        
        return enforced

    def _restructure_nested_subquestions(self, subquestions: list, required_structure: list, template: dict) -> list:
        """
        Restructure flat subquestions into nested structure when template indicates nested pattern.
        For example, Q4: "a) Write SQL Queries to perform the following:" should contain nested i, ii, iii.
        Q3 part (e): "e) [scenario] Write a T-SQL statement..." should contain nested i, ii, iii, iv, v.
        
        Args:
            subquestions: Generated flat subquestions
            required_structure: Template structure (may contain nested items)
            template: Template dict for context
            
        Returns:
            Restructured subquestions with nested items where appropriate
        """
        if not required_structure:
            return subquestions
        
        # Check if any structure item has nested items
        has_nested = any(
            struct_item.get("nested") or struct_item.get("nested_items")
            for struct_item in required_structure
        )
        
        if not has_nested:
            return subquestions
        
        # Find structure items with nested pattern
        restructured = []
        sq_idx = 0
        
        for struct_item in required_structure:
            if struct_item.get("nested") and struct_item.get("nested_items"):
                # This is a parent subquestion with nested items (Q4 pattern)
                # Find the corresponding generated subquestion
                if sq_idx < len(subquestions):
                    parent_sq = subquestions[sq_idx].copy()
                    
                    parent_text = parent_sq.get("text", "").strip()
                    parent_label = parent_sq.get("label", "").lower()
                    
                    # Check if this is Q3 part (e) pattern or Q4 pattern
                    is_q3_e_pattern = (
                        (parent_label == "e" or parent_text.lower().startswith("e)")) and
                        ("financial institution" in parent_text.lower() or "developing a robust database system" in parent_text.lower()) and
                        ("write a t-sql statement" in parent_text.lower() or "write t-sql statement" in parent_text.lower())
                    )
                    is_q4_pattern = "write sql queries" in parent_text.lower() and "following" in parent_text.lower()
                    
                    # Get nested_struct_items from template structure (needed for marks)
                    nested_struct_items = struct_item.get("nested_items", [])
                    
                    # CRITICAL: For Q3 part (e), extract "Write a T-SQL statement..." as nested item i
                    first_nested_item = None
                    if is_q3_e_pattern:
                        # Extract "Write a T-SQL statement..." part as nested item i
                        t_sql_match = re.search(r'(write\s+(?:a\s+)?t-sql\s+statement[^.]*\.)', parent_text, re.IGNORECASE)
                        if t_sql_match:
                            # Get marks from parent or first nested struct item
                            first_item_marks = None
                            if nested_struct_items and len(nested_struct_items) > 0:
                                first_item_marks = nested_struct_items[0].get("marks")
                            if first_item_marks is None:
                                first_item_marks = parent_sq.get("marks")
                            
                            # PRIORITY: Use marks from template structure (past paper distribution)
                            # Check if first nested struct item has marks
                            first_nested_marks = None
                            if nested_struct_items and len(nested_struct_items) > 0:
                                first_nested_marks = nested_struct_items[0].get("marks")
                            # If template doesn't have marks, use parent or default
                            if first_nested_marks is None:
                                first_nested_marks = first_item_marks
                            if first_nested_marks is None:
                                first_nested_marks = 0
                            
                            # Extract T-SQL statement text and ensure no duplicate label
                            t_sql_text = t_sql_match.group(1).strip()
                            # Remove any existing "i. " prefix if present
                            t_sql_text = re.sub(r'^i\.\s*', '', t_sql_text, flags=re.IGNORECASE).strip()
                            
                            first_nested_item = {
                                "label": "i",
                                "marks": int(first_nested_marks),
                                "text": f"i. {t_sql_text}"
                            }
                            # Remove the T-SQL statement part from parent text, keep only scenario
                            parent_text = re.sub(r'write\s+(?:a\s+)?t-sql\s+statement[^.]*\.', '', parent_text, flags=re.IGNORECASE).strip()
                            # Clean up any trailing punctuation
                            parent_text = parent_text.rstrip(".,;").strip()
                            parent_sq["text"] = parent_text
                    # For Q4 pattern, extract "i." from parent text if present
                    elif is_q4_pattern and ("i." in parent_text or "i " in parent_text.lower()):
                        # Extract the "i. Find..." part from parent text
                        i_pattern = r'i\.\s*([^i]+?)(?:\s*$|\s*ii\.|$)'
                        i_match = re.search(i_pattern, parent_text, re.IGNORECASE)
                        if i_match:
                            i_text = i_match.group(1).strip()
                            if i_text and len(i_text) > 10:  # Valid content
                                # Get marks from template or default to 0
                                i_marks = nested_struct_items[0].get("marks") if nested_struct_items and len(nested_struct_items) > 0 else 0
                                first_nested_item = {
                                    "label": "i",
                                    "marks": int(i_marks) if i_marks is not None else 0,
                                    "text": f"i. {i_text}"
                                }
                                # Remove "i. ..." from parent text, keep only "Write SQL Queries to perform the following:"
                                parent_text = re.sub(r'i\.\s*[^i]+?(?:\s*$|\s*ii\.)', '', parent_text, flags=re.IGNORECASE).strip()
                                if not parent_text.endswith(":"):
                                    parent_text = parent_text.rstrip(".,;")
                                    if "following" not in parent_text.lower():
                                        parent_text = "Write SQL Queries to perform the following:"
                    
                    # Ensure parent text follows template pattern
                    if is_q4_pattern and ("write sql queries" not in parent_text.lower() or "following" not in parent_text.lower()):
                        # Force the template pattern
                        parent_sq["text"] = "Write SQL Queries to perform the following:"
                        parent_text = parent_sq["text"]
                    
                    # Create nested subquestions
                    nested_items = []
                    # Add first nested item (i.) if extracted from parent text
                    if first_nested_item:
                        nested_items.append(first_nested_item)
                    
                    # nested_struct_items already defined above (before Q3/Q4 pattern checks)
                    
                    # Collect nested items from generated subquestions
                    for nested_idx, nested_struct in enumerate(nested_struct_items):
                        if sq_idx + 1 + nested_idx < len(subquestions):
                            nested_sq = subquestions[sq_idx + 1 + nested_idx].copy()
                            nested_text = nested_sq.get("text", "").strip()
                            
                            # Extract the nested label from template (ii, iii, etc.)
                            nested_label = nested_struct.get("label", f"ii" if nested_idx == 0 else f"iii" if nested_idx == 1 else "iv")
                            
                            # Remove label prefix from text if present (e.g., "i. ", "ii. ", "iii. ", "iv. ", "v. ")
                            # CRITICAL: Remove ALL possible label patterns to avoid duplication
                            clean_nested_text = nested_text.strip()
                            # Remove patterns like "i. ", "ii. ", "iii. ", "iv. ", "v. " at the start
                            clean_nested_text = re.sub(r'^(i{1,3}|iv|v)\.\s*', '', clean_nested_text, flags=re.IGNORECASE).strip()
                            # Also remove patterns like "i ", "ii ", "iii ", "iv ", "v " (without period)
                            clean_nested_text = re.sub(r'^(i{1,3}|iv|v)\s+', '', clean_nested_text, flags=re.IGNORECASE).strip()
                            # Remove any duplicate label patterns that might remain
                            clean_nested_text = re.sub(r'^(i{1,3}|iv|v)\.\s*(i{1,3}|iv|v)\.\s*', r'\2. ', clean_nested_text, flags=re.IGNORECASE).strip()
                            
                            # For Q4 pattern, ensure it starts with "Find" or "Write SQL queries to find"
                            if is_q4_pattern:
                                if not clean_nested_text.lower().startswith(("find", "write sql queries")):
                                    # Try to extract the query part
                                    if "find" in clean_nested_text.lower():
                                        find_pos = clean_nested_text.lower().find("find")
                                        query_part = clean_nested_text[find_pos + 4:].strip()
                                        clean_nested_text = f"Find {query_part}"
                            # For Q3 part (e), keep the text as-is (it should be "Provide Sarah...", "Assuming Emily...", etc.)
                            # No need to modify the text for Q3 part (e)
                            
                            # Create nested item with proper label
                            # PRIORITY: Use marks from template structure (past paper distribution)
                            # If template has marks, use them; otherwise use generated marks; fallback to 0
                            nested_marks = nested_struct.get("marks")
                            if nested_marks is None:
                                nested_marks = nested_sq.get("marks")
                            if nested_marks is None:
                                nested_marks = 0
                            
                            # CRITICAL: Text should NOT include label prefix - PDF renderer will add it based on the "label" field
                            # Remove any remaining label prefixes (handle cases like "i. i. " or "ii. ii. ")
                            while True:
                                old_text = clean_nested_text
                                # Remove label prefixes (with period or space) - remove ALL occurrences
                                clean_nested_text = re.sub(r'^(i{1,3}|iv|v)[\.\s]+\s*', '', clean_nested_text, flags=re.IGNORECASE).strip()
                                if clean_nested_text == old_text:
                                    break  # No more labels to remove
                            
                            # Use clean text WITHOUT label prefix (label is stored separately in "label" field)
                            final_text = clean_nested_text
                            
                            nested_items.append({
                                "label": nested_label,
                                "marks": int(nested_marks),
                                "text": final_text
                            })
                        else:
                            # Use template structure if generated subquestion doesn't exist
                            nested_text = nested_struct.get("text", "").strip()
                            nested_label = nested_struct.get("label", f"ii" if nested_idx == 0 else f"iii" if nested_idx == 1 else "iv")
                            nested_items.append({
                                "label": nested_label,
                                "marks": int(nested_struct.get("marks") or 0),
                                "text": nested_text
                            })
                    
                    # Add nested items to parent
                    parent_sq["subquestions"] = nested_items
                    # CRITICAL: For ANY parent with nested subquestions, parent should have null marks
                    # The marks are distributed among nested items, not the parent
                    if nested_items:  # If there are nested items, parent should have None marks
                        parent_sq["marks"] = None  # Parent has no marks when nested items have marks
                    else:
                        # Only set marks if there are NO nested items
                        # Ensure parent marks is never None (default to 0 if missing)
                        parent_marks = struct_item.get("marks")
                        parent_sq["marks"] = int(parent_marks) if parent_marks is not None else 0
                    restructured.append(parent_sq)
                    sq_idx += 1 + len(nested_items)  # Skip the nested items in main list
                else:
                    # Parent subquestion doesn't exist, create it from template
                    parent_sq = {
                        "label": struct_item.get("label", "a"),
                        "marks": struct_item.get("marks"),
                        "text": "Write SQL Queries to perform the following:",
                        "subquestions": []
                    }
                    
                    # Add nested items from template
                    for nested_struct in struct_item.get("nested_items", []):
                        parent_sq["subquestions"].append({
                            "label": nested_struct.get("label", "ii"),
                            "marks": nested_struct.get("marks", 0),
                            "text": nested_struct.get("text", "")
                        })
                    
                    restructured.append(parent_sq)
            else:
                # Regular subquestion (not nested)
                if sq_idx < len(subquestions):
                    restructured.append(subquestions[sq_idx])
                    sq_idx += 1
                else:
                    # Add from template if doesn't exist
                    template_marks = struct_item.get("marks")
                    restructured.append({
                        "label": struct_item.get("label", "?"),
                        "marks": int(template_marks) if template_marks is not None else 0,
                        "text": struct_item.get("text", "")
                    })
        
        return restructured

    def _handle_code_segment_references(self, parsed: dict, template: dict, slot: dict) -> dict:
        """
        Detect subquestions that reference "code segment given below" and add appropriate SQL code.
        Checks both generated text AND template structure to ensure code segments are added.
        
        Args:
            parsed: Generated question dict with text and subquestions
            template: Template dict for context
            slot: Slot dict for question metadata
            
        Returns:
            Updated parsed dict with code segments inserted
        """
        subquestions = parsed.get("subquestions", [])
        question_text = parsed.get("text", "")
        pattern_label = template.get("pattern_label", "").lower()
        required_structure = template.get("required_structure", [])
        
        # Check each subquestion for "code segment given below" references
        for idx, sq in enumerate(subquestions):
            sq_text = sq.get("text", "").lower()
            sq_label = sq.get("label", "")
            
            # Check if template structure has "code segment given below" for this subquestion
            template_has_code_ref = False
            if idx < len(required_structure):
                template_text = required_structure[idx].get("text", "").lower()
                template_has_code_ref = "code segment given below" in template_text or "code segment" in template_text
            
            # Detect references to code segments in generated text
            code_ref_patterns = [
                r"code segment given below",
                r"code snippet given below",
                r"code example given below",
                r"code given below",
                r"segment given below",
                r"statement.*given below"
            ]
            
            has_code_ref = any(re.search(pattern, sq_text) for pattern in code_ref_patterns)
            
            # If template has code segment reference OR generated text has it, add the code
            if has_code_ref or template_has_code_ref:
                if template_has_code_ref and not has_code_ref:
                    self.log(f"    🔍 Template requires code segment for subquestion {sq_label} (template has 'code segment given below')")
                else:
                    self.log(f"    🔍 Detected code segment reference in subquestion {sq_label}")
                
                # Generate appropriate code snippet based on question context
                sql_code = self._generate_sql_code_for_context(question_text, pattern_label, sq_text)
                
                if sql_code:
                    original_text = sq.get("text", "")
                    
                    # If generated text doesn't have "code segment given below", add it to the question
                    if not has_code_ref and template_has_code_ref:
                        # Template requires code segment but generated text doesn't mention it
                        # Add the code segment and update the question to reference it
                        # Check if question asks about "which type of statement" or similar
                        if "which" in sq_text and ("statement" in sq_text or "type" in sq_text):
                            # This is likely a JDBC/SQL statement type question
                            # CRITICAL: Follow past paper template exactly - remove any hints that give away the answer
                            # Template: "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                            # DO NOT include hints like "SQL statements are used to..." or "DDL is used to..." - these give away the answer
                            
                            # Remove hints that give away the answer
                            updated_text = original_text
                            # Remove phrases like "SQL statements are used to create tables" or "DDL is used to define"
                            updated_text = re.sub(r'(sql\s+data\s+definition\s+language|ddl|sql\s+statements?)\s+(is\s+used\s+to|are\s+used\s+to|is\s+used\s+for|are\s+used\s+for)[^?]*[.,]?\s*', '', updated_text, flags=re.IGNORECASE)
                            updated_text = re.sub(r'these?\s+statements?\s+(are\s+used\s+to|is\s+used\s+to|are\s+used\s+for|is\s+used\s+for)[^?]*[.,]?\s*', '', updated_text, flags=re.IGNORECASE)
                            updated_text = re.sub(r'to\s+create\s+the\s+tables?\s+mentioned\s+in\s+this\s+scenario[^?]*[.,]?\s*', '', updated_text, flags=re.IGNORECASE)
                            
                            # Ensure it follows the exact template pattern: "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                            if "which type" in updated_text.lower():
                                # Extract the "which type" question part
                                which_match = re.search(r'which\s+type[^?]*\?', updated_text, re.IGNORECASE)
                                if which_match:
                                    # Use the exact template pattern
                                    updated_text = "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                                else:
                                    updated_text = "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                            else:
                                # If "which type" is missing, add it using the template
                                updated_text = "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
                        else:
                            updated_text = original_text
                    else:
                        # Update the subquestion text to reference "shown above" instead of "given below"
                        updated_text = re.sub(
                            r"(code segment|code snippet|code example|code|segment)\s+given below",
                            r"\1 shown above",
                            original_text,
                            flags=re.IGNORECASE
                        )
                        
                        # CRITICAL: Also remove hints that give away the answer (for Q3 subquestion b)
                        if "which" in updated_text.lower() and ("statement" in updated_text.lower() or "type" in updated_text.lower()):
                            # Remove hints like "SQL statements are used to..." or "DDL is used to..."
                            hint_patterns = [
                                r'sql\s+data\s+definition\s+language[^?]*[.,]?\s*',
                                r'ddl\s+is\s+used\s+to[^?]*[.,]?\s*',
                                r'sql\s+statements?\s+are\s+used\s+to[^?]*[.,]?\s*',
                                r'these?\s+statements?\s+are\s+used\s+to[^?]*[.,]?\s*',
                                r'to\s+create\s+the\s+tables?\s+mentioned[^?]*[.,]?\s*'
                            ]
                            for pattern in hint_patterns:
                                updated_text = re.sub(pattern, '', updated_text, flags=re.IGNORECASE)
                            # Clean up multiple spaces
                            updated_text = re.sub(r'\s+', ' ', updated_text).strip()
                            
                            # Ensure it follows the exact template pattern
                            if "which type" in updated_text.lower() and "briefly explain" in updated_text.lower():
                                # Keep it but ensure it matches template
                                if "code segment" not in updated_text.lower():
                                    updated_text = "Which type of statements is used in the code segment shown above? Briefly explain when this type of statement will be used."
                            elif "which type" not in updated_text.lower():
                                updated_text = "Which type of statements is used in the code segment shown above? Briefly explain when this type of statement will be used."
                    
                    # Use java fence for JDBC snippets, sql otherwise.
                    code_lang = "java" if ("preparedstatement" in sql_code.lower() or "resultset" in sql_code.lower() or "connection.preparestatement" in sql_code.lower()) else "sql"

                    # If generated code is JDBC-style, keep wording JDBC-specific (not generic SQL-DML phrasing).
                    if code_lang == "java":
                        updated_text = re.sub(
                            r"there are several different types of statements in sql for data manipulation\.\s*",
                            "",
                            updated_text,
                            flags=re.IGNORECASE,
                        )
                        updated_text = (
                            "Which type of JDBC statement is used in the code segment shown above? "
                            "Briefly explain when this type of statement will be used."
                        )

                    # Insert code block directly into the subquestion text
                    # Format: Code block first, then the question text on the next line
                    code_block = f"Code Segment:\n```{code_lang}\n{sql_code}\n```\n"
                    
                    # Prepend code block to subquestion text with newline separation
                    sq["text"] = code_block + "\n" + updated_text
                    self.log(f"    ✅ Added SQL code segment to subquestion {sq_label}")
        
        return parsed

    def _fix_subquestion_references(self, parsed: dict, template: dict) -> dict:
        """
        Fix references like "queries (i) to (iv)" when subquestions are labeled a, b, c, d instead.
        This happens when nested subquestions (a.i, a.ii, etc.) are flattened to a, b, c, d.
        
        Args:
            parsed: Generated question dict with text and subquestions
            template: Template dict for context
            
        Returns:
            Updated parsed dict with fixed references
        """
        subquestions = parsed.get("subquestions", [])
        pattern_label = template.get("pattern_label", "").lower()
        
        # Only fix for relational algebra questions (where this pattern occurs)
        if "relational_algebra" not in pattern_label and "relational algebra" not in pattern_label:
            return parsed
        
        # Check each subquestion for references to (i), (ii), (iii), (iv), etc.
        for idx, sq in enumerate(subquestions):
            sq_text = sq.get("text", "")
            
            # Detect references to roman numeral or letter subquestions
            ref_patterns = [
                r"queries?\s*\(([ivx]+)\)\s*to\s*\(([ivx]+)\)",  # queries (i) to (iv)
                r"above\s+queries?\s*\(([ivx]+)\)\s*to\s*\(([ivx]+)\)",  # above queries (i) to (iv)
                r"queries?\s*\(([a-z])\)\s*to\s*\(([a-z])\)",  # queries (a) to (d) - already correct
            ]
            
            for pattern in ref_patterns:
                match = re.search(pattern, sq_text, re.IGNORECASE)
                if match:
                    start_ref = match.group(1).lower()
                    end_ref = match.group(2).lower()
                    
                    # Map roman numerals to letters: i=0, ii=1, iii=2, iv=3, v=4
                    roman_to_idx = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5}
                    
                    start_idx = roman_to_idx.get(start_ref, None)
                    end_idx = roman_to_idx.get(end_ref, None)
                    
                    if start_idx is not None and end_idx is not None:
                        # Convert to actual subquestion labels (a, b, c, d, e, f)
                        # Assuming the first N subquestions are the relational algebra queries
                        # and the last one is the tuple calculus question
                        if start_idx < len(subquestions) - 1 and end_idx < len(subquestions) - 1:
                            start_label = chr(ord('a') + start_idx)
                            end_label = chr(ord('a') + end_idx)
                            
                            # Replace the reference
                            new_text = re.sub(
                                pattern,
                                f"queries ({start_label}) to ({end_label})",
                                sq_text,
                                flags=re.IGNORECASE
                            )
                            
                            sq["text"] = new_text
                            self.log(f"    🔧 Fixed subquestion reference: ({start_ref}) to ({end_ref}) -> ({start_label}) to ({end_label}) in subquestion {sq.get('label', idx)}")
                            break
        
        return parsed
    
    def _fix_q3_scenario_placement(self, parsed: dict, template: dict, slot: dict) -> dict:
        """
        Fix Q3 scenario placement: scenario paragraph should be above part (c), not part (a).
        
        The scenario: "A university is developing a database system to manage its student records, 
        courses, and faculty details efficiently. The database will include tables for students, 
        courses, enrollments, and faculty. Each student can enroll in multiple courses, and each 
        course can have multiple students. The faculty members will manage the courses and assign 
        grades to the students. The database administrator is responsible for creating the database 
        schema and ensuring its integrity and security. Write necessary SQL statements to maintain 
        the database system."
        
        This should be placed above part (c), not part (a).
        """
        q_no = slot.get("question_no") or slot.get("slot_id", "")
        if q_no not in ["Q3", "3"]:
            return parsed
        
        subquestions = parsed.get("subquestions", [])
        if len(subquestions) < 3:
            return parsed
        
        # Find part (c) - index 2 (0-indexed: a=0, b=1, c=2)
        part_c = None
        part_c_idx = None
        for idx, sq in enumerate(subquestions):
            label = sq.get("label", "").lower().strip()
            if label == "c" or (isinstance(label, str) and label.strip().rstrip(")") == "c"):
                part_c = sq
                part_c_idx = idx
                break
        
        if not part_c or part_c_idx is None:
            return parsed
        
        # Check if part (c) text contains "Write necessary SQL statements" or similar
        part_c_text = part_c.get("text", "").lower()
        needs_scenario = (
            "write necessary sql statements" in part_c_text or
            "write sql statements" in part_c_text or
            "write necessary" in part_c_text
        )
        
        if not needs_scenario:
            return parsed
        
        # Check if scenario is already in part (c) text
        scenario_keywords = ["university", "developing", "database system", "student records", "courses", "faculty"]
        has_scenario = any(keyword in part_c_text for keyword in scenario_keywords)
        
        # Check part (a) for scenario
        part_a = subquestions[0] if len(subquestions) > 0 else None
        if part_a:
            part_a_text = part_a.get("text", "")
            part_a_has_scenario = any(keyword in part_a_text.lower() for keyword in scenario_keywords)
            
            if part_a_has_scenario and not has_scenario:
                # Scenario is in part (a) but should be in part (c) - move it
                # Extract scenario from part (a) - scenario typically ends before "In Type 2 Driver" or "JDBC"
                scenario_pattern = r'(A\s+university.*?)(?:In\s+Type\s+2\s+Driver|JDBC|Accept\s+or\s+refute|which\s+type)'
                scenario_match = re.search(scenario_pattern, part_a_text, re.IGNORECASE | re.DOTALL)
                if scenario_match:
                    scenario_text = scenario_match.group(1).strip()
                    # Remove scenario from part (a) - keep only the JDBC statement
                    part_a["text"] = re.sub(scenario_pattern, r'\2', part_a_text, flags=re.IGNORECASE | re.DOTALL).strip()
                    # Clean up any leading/trailing whitespace
                    part_a["text"] = part_a["text"].strip()
                    # Add scenario to part (c)
                    current_c_text = part_c.get("text", "")
                    if scenario_text not in current_c_text:
                        part_c["text"] = scenario_text + "\n\n" + current_c_text
                        self.log(f"    🔧 Moved scenario from Q3 part (a) to part (c)")
            elif part_a_has_scenario and has_scenario:
                # Scenario is in both - remove from part (a)
                scenario_pattern = r'(A\s+university.*?)(?:In\s+Type\s+2\s+Driver|JDBC|Accept\s+or\s+refute|which\s+type)'
                part_a["text"] = re.sub(scenario_pattern, r'\2', part_a_text, flags=re.IGNORECASE | re.DOTALL).strip()
                part_a["text"] = part_a["text"].strip()
                self.log(f"    🔧 Removed scenario from Q3 part (a) - scenario should only be in part (c)")
        
        # 2. Handle part (e) scenario placement - ensure scenario stays in part (e) parent text
        part_e = None
        for idx, sq in enumerate(subquestions):
            label = sq.get("label", "").lower().strip()
            if label == "e" or (isinstance(label, str) and label.strip().rstrip(")") == "e"):
                part_e = sq
                break
        
        if part_e:
            part_e_text = part_e.get("text", "")
            # Check if part (e) has the financial institution scenario or healthcare scenario
            has_financial_scenario = (
                "financial institution" in part_e_text.lower() or
                "developing a robust database system" in part_e_text.lower()
            )
            has_healthcare_scenario = (
                "healthcare organization" in part_e_text.lower() or
                "healthcare" in part_e_text.lower() and "database system" in part_e_text.lower()
            )
            
            # The scenario should be in the parent part (e) text, before "Write a T-SQL statement"
            # Ensure scenario is not moved to nested items
            if has_financial_scenario or has_healthcare_scenario:
                # Check nested subquestions if they exist
                nested_subs = part_e.get("subquestions", [])
                for nested_sq in nested_subs:
                    nested_text = nested_sq.get("text", "")
                    # If a nested item has the scenario keywords but shouldn't (scenario should be in parent)
                    if ("financial institution" in nested_text.lower() or "healthcare organization" in nested_text.lower()) and "write a t-sql statement" not in nested_text.lower():
                        # Remove scenario from nested item - it should only be in parent
                        nested_sq["text"] = re.sub(r'A\s+(?:financial\s+institution|healthcare\s+organization).*?\.', '', nested_text, flags=re.IGNORECASE | re.DOTALL).strip()
                        self.log(f"    🔧 Removed scenario from Q3 part (e) nested item - scenario should be in parent text")
            
            # Ensure the scenario paragraph is properly placed in parent text
            # Scenario should come before "Write a T-SQL statement" in the parent text
            if "write a t-sql statement" in part_e_text.lower() or "write t-sql statement" in part_e_text.lower():
                # Check if scenario is before the T-SQL statement
                t_sql_pos = part_e_text.lower().find("write")
                if t_sql_pos > 0:
                    scenario_part = part_e_text[:t_sql_pos].strip()
                    # If scenario is present and properly positioned, log success
                    if len(scenario_part) > 50 and ("financial institution" in scenario_part.lower() or "healthcare organization" in scenario_part.lower() or "developing" in scenario_part.lower()):
                        self.log(f"    ✅ Q3 part (e) scenario is correctly placed in parent text above nested subquestions")
        
        # 3. CRITICAL: Remove healthcare/financial institution scenario from main question text
        # The scenario should ONLY be in part (e), not in the main question text
        main_text = parsed.get("text", "")
        if main_text:
            # Check for healthcare organization scenario in main text
            healthcare_patterns = [
                r'A\s+healthcare\s+organization\s+is\s+implementing.*?system\.',
                r'A\s+healthcare\s+organization\s+aims\s+to\s+manage.*?system\.',
                r'Different\s+roles\s+are\s+assigned\s+to\s+team\s+members.*?system\.',
            ]
            
            # Check for financial institution scenario in main text
            financial_patterns = [
                r'A\s+financial\s+institution.*?system\.',
                r'A\s+software\s+company.*?system\.',
            ]
            
            # Remove healthcare scenario from main text if present
            for pattern in healthcare_patterns:
                if re.search(pattern, main_text, re.IGNORECASE | re.DOTALL):
                    # Check if part (e) has the scenario (it should)
                    if part_e and ("healthcare" in part_e.get("text", "").lower() or "healthcare organization" in part_e.get("text", "").lower()):
                        # Remove from main text
                        main_text = re.sub(pattern, '', main_text, flags=re.IGNORECASE | re.DOTALL).strip()
                        # Clean up multiple spaces and newlines
                        main_text = re.sub(r'\s+', ' ', main_text).strip()
                        parsed["text"] = main_text
                        self.log(f"    🔧 Removed healthcare scenario from Q3 main question text - scenario should only be in part (e)")
                        break
            
            # Remove financial institution scenario from main text if present
            for pattern in financial_patterns:
                if re.search(pattern, main_text, re.IGNORECASE | re.DOTALL):
                    # Check if part (e) has the scenario (it should)
                    if part_e and ("financial institution" in part_e.get("text", "").lower() or "developing a robust database system" in part_e.get("text", "").lower()):
                        # Remove from main text
                        main_text = re.sub(pattern, '', main_text, flags=re.IGNORECASE | re.DOTALL).strip()
                        # Clean up multiple spaces and newlines
                        main_text = re.sub(r'\s+', ' ', main_text).strip()
                        parsed["text"] = main_text
                        self.log(f"    🔧 Removed financial institution scenario from Q3 main question text - scenario should only be in part (e)")
                        break
        
        parsed["subquestions"] = subquestions
        return parsed

    def _generate_sql_code_for_context(self, question_text: str, pattern_label: str, subquestion_text: str) -> str:
        """
        Generate appropriate SQL code based on question context.
        Makes code segments more complex to match past paper patterns.
        
        Args:
            question_text: Main question text
            pattern_label: Topic/pattern label
            subquestion_text: Subquestion text for context
            
        Returns:
            SQL code string or empty string if no code needed
        """
        import re
        
        # Determine SQL code type based on context
        question_lower = question_text.lower()
        sq_lower = subquestion_text.lower()
        
        # Extract table names from question text for context-aware code generation.
        # Keep deterministic order and sanitize identifiers to avoid invalid names like "and".
        schema_tables = []
        seen_tables = set()

        def _add_table(name: str):
            cleaned = (name or "").strip()
            if not cleaned:
                return
            # Keep only valid SQL identifiers and drop conjunction/noise words.
            cleaned = re.sub(r'[^A-Za-z0-9_]', '', cleaned)
            if not cleaned or cleaned.lower() in {"and", "table", "tables"}:
                return
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', cleaned):
                return
            if cleaned.lower() not in seen_tables:
                seen_tables.add(cleaned.lower())
                schema_tables.append(cleaned)

        # METHOD 1: explicit table declarations: "TableName(attr1, ...)"
        table_pattern = r'\b([A-Za-z_][A-Za-z0-9_]*)\s*\('
        for match in re.findall(table_pattern, question_text):
            _add_table(match)

        # METHOD 2: narrative list: "tables for Products, Orders, Customers, and OrderDetails"
        narrative_pattern = r'tables?\s+for\s+([^.;\n]+)'
        narrative_match = re.search(narrative_pattern, question_text, re.IGNORECASE)
        if narrative_match:
            tables_str = narrative_match.group(1)
            # Normalize "and X" to ", X" then split.
            tables_str = re.sub(r'\band\b', ',', tables_str, flags=re.IGNORECASE)
            for candidate in tables_str.split(','):
                _add_table(candidate)

        # Use extracted tables if available, otherwise fallback defaults.
        primary_table = schema_tables[0] if schema_tables else "Students"
        secondary_table = schema_tables[1] if len(schema_tables) > 1 else "Departments"
        
        # Check what type of SQL statement is being asked about.
        # For Q3(b)-style prompts ("which type of statements ... code segment"),
        # always generate JDBC Java snippets to match past paper format.
        is_jdbc_style_prompt = (
            "jdbc" in sq_lower
            or "jdbc api" in sq_lower
            or "result set" in sq_lower
            or (
                ("which type of statements" in sq_lower or ("which type" in sq_lower and "statement" in sq_lower))
                and ("code segment" in sq_lower or "code snippet" in sq_lower or "shown above" in sq_lower or "given below" in sq_lower)
            )
        )
        if is_jdbc_style_prompt:
            jdbc_context = f"{question_lower} {sq_lower}"
            # If the prompt/scenario suggests data-modification, return executeUpdate style.
            if any(k in jdbc_context for k in ["insert", "update", "delete", "executeupdate", "rowsaffected"]):
                return """String sql = "INSERT INTO employees (id, name, age) VALUES (101, 'John Doe', 30)";
try {
    int rowsAffected = statement.executeUpdate(sql);
    if (rowsAffected > 0) {
        System.out.println("A new record has been inserted successfully!");
    } else {
        System.out.println("Failed to insert a new record!");
    }
} catch (SQLException e) {
    e.printStackTrace();
}"""
            # Default Q3(b)-like pattern: result-set retrieval snippet.
            return """String sql = "SELECT * FROM employees WHERE department = ?";
PreparedStatement pstmt = connection.prepareStatement(sql);
pstmt.setString(1, "IT");
ResultSet rs = pstmt.executeQuery();"""
        
        elif "dml" in sq_lower or "data manipulation" in sq_lower or "insert" in sq_lower or "update" in sq_lower or "delete" in sq_lower:
            # DML statement - make more complex with multiple operations
            return f"""UPDATE {primary_table} 
SET Age = 25, Status = 'Active', LastModified = GETDATE()
WHERE {primary_table}ID = 'P001';

INSERT INTO {primary_table} ({primary_table}ID, Name, Age, {secondary_table}ID)
VALUES ('P002', 'John Doe', 30, 'D001');"""
        
        elif "ddl" in sq_lower or "data definition" in sq_lower or "create table" in sq_lower:
            # DDL statement - make it complex like past paper patterns
            # Include multiple constraints: PRIMARY KEY, NOT NULL, UNIQUE, DEFAULT, FOREIGN KEY, CHECK
            return f"""CREATE TABLE {primary_table} (
    {primary_table}ID CHAR(10) PRIMARY KEY,
    Name VARCHAR(50) NOT NULL,
    NIC CHAR(10) UNIQUE,
    Age INT,
    GPA FLOAT,
    {secondary_table}ID VARCHAR(10) DEFAULT 'D001',
    EnrollmentDate DATE DEFAULT GETDATE(),
    CONSTRAINT {primary_table.lower()}_{secondary_table.lower()}_fk FOREIGN KEY ({secondary_table}ID)
        REFERENCES {secondary_table}({secondary_table}ID) 
        ON DELETE SET DEFAULT 
        ON UPDATE CASCADE,
    CONSTRAINT gpa_check CHECK (GPA >= 0.0 AND GPA <= 4.0),
    CONSTRAINT age_check CHECK (Age >= 18 AND Age <= 100)
);"""
        
        elif "select" in sq_lower or "query" in sq_lower or "retrieve" in sq_lower:
            # SELECT statement - make more complex with JOINs and aggregations
            if len(schema_tables) >= 2:
                return f"""SELECT {primary_table}.{primary_table}ID, {primary_table}.Name, {secondary_table}.{secondary_table}Name
FROM {primary_table}
INNER JOIN {secondary_table} ON {primary_table}.{secondary_table}ID = {secondary_table}.{secondary_table}ID
WHERE {primary_table}.Age > 18
ORDER BY {primary_table}.Name;"""
            else:
                return f"""SELECT {primary_table}ID, Name, Age 
FROM {primary_table} 
WHERE Age > 18 AND Status = 'Active'
ORDER BY Name DESC
LIMIT 10;"""
        
        elif "t-sql" in sq_lower or "transact-sql" in sq_lower:
            # T-SQL statement - make more complex
            return f"""SELECT {primary_table}ID, Name, Age, 
       CASE 
           WHEN Age < 25 THEN 'Young'
           WHEN Age BETWEEN 25 AND 65 THEN 'Adult'
           ELSE 'Senior'
       END AS AgeCategory
FROM {primary_table}
WHERE Age BETWEEN 18 AND 65
ORDER BY Age;"""
        
        else:
            # Default: Complex SQL with multiple statements
            return f"""CREATE TABLE {primary_table} (
    {primary_table}ID INT PRIMARY KEY IDENTITY(1,1),
    Name VARCHAR(50) NOT NULL,
    Email VARCHAR(100) UNIQUE,
    Age INT CHECK (Age >= 18),
    Status VARCHAR(20) DEFAULT 'Active'
);

INSERT INTO {primary_table} (Name, Email, Age)
VALUES ('John Smith', 'john@example.com', 25);"""

    def _build_generation_prompt(self, slot, template, context, global_context, feedback=None, *, banned_topics=None) -> str:
        """Mode 1: Pure Generation from Constraints (No past text shown)."""
        
        q_no = slot.get("question_no") or slot.get("slot_id", "")
        topic = slot.get('topics', ['General'])[0]
        structure_fingerprint = template.get("required_structure") or [{"label": "a", "marks": slot.get("target_marks")}]
        pattern_label = template.get('pattern_label', topic).lower()
        
        # Calculate sub-question breakdown string with text patterns if available
        structure_parts = []
        instruction_patterns = []  # Store patterns for explicit enforcement
        for s in structure_fingerprint:
            label = s.get('label', '?')
            marks = s.get('marks', 0)
            text_pattern = s.get('text', '')  # Get stored text pattern
            if text_pattern:
                # Clean text pattern (remove label prefix if present)
                clean_pattern = text_pattern.strip()
                if clean_pattern and len(clean_pattern) > 2 and clean_pattern[1] in [')', '.', '?']:
                    clean_pattern = clean_pattern[2:].strip()
                
                # For SQL_DDL_DML questions, if pattern starts with "Find", convert to "Write SQL queries"
                pattern_label_lower = template.get('pattern_label', '').lower()
                if "sql" in pattern_label_lower and clean_pattern.lower().startswith("find"):
                    # Extract the query requirement part
                    if "find" in clean_pattern.lower():
                        # Convert "Find X" to "Write SQL queries to find X"
                        query_part = clean_pattern.split("Find", 1)[1].strip() if "Find" in clean_pattern else clean_pattern.split("find", 1)[1].strip()
                        clean_pattern = f"Write SQL queries to find {query_part}"
                
                instruction_patterns.append(clean_pattern)
                # Include the instruction pattern for preservation
                structure_parts.append(f"- Part {label}: {marks} marks\n  Instruction Pattern (MUST PRESERVE EXACTLY): \"{clean_pattern}\"")
            else:
                structure_parts.append(f"- Part {label}: {marks} marks")
                instruction_patterns.append("")
        structure_str = "\n".join(structure_parts)
        
        # CRITICAL: Get exact count required
        required_count = len(structure_fingerprint)
        
        # Determine if ER/EER, Normalization, or Relational Algebra question
        is_er_question = "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label or "schema" in pattern_label
        is_norm_question = "normalization" in pattern_label or "normal form" in pattern_label
        is_rel_algebra_question = "relational algebra" in pattern_label or "relational_algebra" in pattern_label or "tuple calculus" in pattern_label
        
        
        er_context = ""
        if is_er_question:
             er_context = "Include a scenario describing entities, relationships, and attributes."
        elif is_norm_question:
             er_context = "Include a relation schema and functional dependencies."
        elif is_rel_algebra_question:
             er_context = "Include a relational database schema with ALL relations and their attributes listed explicitly (e.g., 'passenger (pid, pname, pgender, pcity)', 'booking (pid, aid, fid, fdate)')."
        else:
             er_context = "Include relevant context and background information."

        prompt = f"""
        You are an expert Exam Setter for a Database Management Systems course.
        Create a NEW, ORIGINAL exam question STRICTLY based on historical exam patterns, topic coverage, and syllabus modules.
        
        ⚠️ CRITICAL: SYLLABUS ALIGNMENT REQUIREMENTS ⚠️
        - Generate questions STRICTLY based on historical exam patterns from past papers
        - All questions MUST be directly aligned with past exam content and curriculum requirements
        - Ensure questions reflect ONLY core Database Management Systems syllabus content
        - Follow the exact structure and style of historical exam questions
        - Do NOT introduce topics unrelated to the core syllabus or past paper patterns
        
        ⚠️ CRITICAL: NO HINTS OR ANSWERS IN QUESTIONS ⚠️
        - Questions MUST challenge students' understanding and require them to apply knowledge
        - DO NOT include hints, answers, or solution steps within the question text
        - DO NOT state what type of statement/query/approach is used - ask the student to identify it
        - DO NOT say "SQL statements are used to..." - instead ask "Which type of statements is used..."
        - DO NOT include phrases that give away the answer (e.g., "SQL statements are used to create tables" - this tells the answer)
        - Questions should assess problem-solving abilities, not provide solutions
        - Example CORRECT: "Which type of statements is used in the code segment given below? Briefly explain when this type of statement will be used."
        - Example INCORRECT: "SQL statements are used to create the tables mentioned in this scenario. Which type of statements is used..."
        - Focus on asking questions that require students to analyze, identify, explain, or solve - not questions that tell them what to do
        
        🚫 STRICT NON-DATABASE TOPIC PROHIBITION 🚫
        ABSOLUTELY DO NOT include any topics from:
        - Networking: TCP/IP, routing, switching, packets, datagrams, OSI model, network layers, sockets, DNS, DHCP, VPN, firewall
        - Operating Systems: CPU scheduling, process scheduling, memory management, file systems, semaphores, mutexes, threads, processes
        - Web Development: HTML, CSS, JavaScript, frontend, backend, web development
        - Compiler Design: Compiler, interpreter, syntax, parsing, lexical analysis
        - Software Engineering: Agile, Scrum, Waterfall, SDLC, software engineering methodologies
        - Machine Learning & AI: Neural networks, deep learning, machine learning, AI algorithms
        - Any other topics NOT in Database Management Systems curriculum
        
        ALL questions MUST remain within Database Management Systems (DMS) scope ONLY.

        TOOLING RULES (STRICT):
        - Do NOT output Mermaid, Graphviz, Kroki links, or any external-diagram syntax.
        - Do NOT include code fences like ```mermaid.
        - If a diagram would normally be required, phrase it as a normal exam instruction in plain text (e.g., "Draw an ER diagram...") without any generated diagram code.
        
        METADATA:
        - Question No: {slot.get('question_no', '?')}
        - Total Marks: {slot.get('target_marks')}
        - Primary Topic: {template.get('pattern_label', topic)}
        - Historical Pattern: This template is derived from past exam papers - follow its structure EXACTLY
        - Module Context: {context[:500]}...

        TOPIC UNIQUENESS (STRICT):
        - This question's topic MUST be: {template.get('pattern_label', topic)}
        - This topic is derived from historical exam patterns - maintain alignment
        - BANNED TOPICS (must NOT be used): {banned_topics or []}
        
        GLOBAL ANTI-REPETITION CONSTRAINTS (DO NOT REUSE):
        - BANNED TOPICS (MUST NOT REPEAT): {global_context.get('banned_topics', [])} (You MUST use a DIFFERENT topic - each question must have a unique topic)
        - USED QUESTION TYPES: {global_context.get('used_question_types', [])} (You MUST generate a DIFFERENT type)
        - USED SCENARIOS: {global_context.get('used_scenarios', [])} (You MUST use a completely different scenario)
        
        REQUIRED STRUCTURE (MANDATORY - NO EXCEPTIONS):
{structure_str}
        
        ⚠️ CRITICAL: You MUST generate EXACTLY {required_count} sub-questions matching this structure.
        - If template shows 9 parts, you MUST generate 9 sub-questions
        - If template shows 7 parts, you MUST generate 7 sub-questions
        - Any other count will be REJECTED immediately
        - The number of sub-questions MUST match the template structure EXACTLY
        
        🚨 INSTRUCTION PATTERN PRESERVATION (CRITICAL - ZERO TOLERANCE):
        - For each sub-question, look at the "Instruction Pattern (MUST PRESERVE EXACTLY)" shown above
        - You MUST use the EXACT instruction type from the pattern:
          * If pattern says "Create a function", you MUST say "Create a function" (NOT "Create a procedure" or "Create a SQL command")
          * If pattern says "Create a trigger", you MUST say "Create a trigger" (NOT "Create a procedure" or "Create a SQL command")
          * If pattern says "Find the member", you MUST use "Find" (NOT "List" or "Retrieve")
          * If pattern says "Briefly explain", you MUST use "Briefly explain" (NOT "Explain" or "Describe")
        - Only change scenario-specific details (entity names, table names, attribute names, organization names)
        - Keep ALL instruction verbs, qualifiers, and structure EXACTLY as shown in the pattern
        - Example: If pattern is "Create a function to calculate...", your output MUST start with "Create a function to calculate..." (change only the calculation details, not the instruction type)
        
        CRITICAL CONSTRAINTS (ZERO TOLERANCE - VIOLATIONS WILL CAUSE REJECTION):
        1. **NO PLACEHOLDERS**: Never use "...", "TBD", "[insert", "[placeholder", or any placeholder text. Every field must have complete, valid content.
        2. **MARKS MUST SUM EXACTLY**: Sub-question marks must sum to exactly {slot.get('target_marks')}. Double-check your math.
        3. **EACH SUBQUESTION MUST BE SEMANTICALLY DISTINCT**: Use different task verbs/intents (e.g., "define", "identify", "draw", "analyze", "calculate"). No duplicate or near-duplicate questions.
        4. **NO "DESCRIBED ABOVE" REFERENCES**: Never say "described above", "as shown above", "diagram above" unless you have already included the described content in the question stem.
        5. **VALID JSON ONLY**: Output must be valid JSON matching the exact schema below. No syntax errors.
        
        {"6. **ER/EER QUESTION REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if is_er_question else ""}{"The question stem MUST include a COMPREHENSIVE scenario block (4-7 sentences) describing:" if is_er_question else ""}
        {"   - MINIMUM 4 distinct entities with their attributes (at least 4 entities)" if is_er_question else ""}
        {"   - ⚠️ CRITICAL: Each entity MUST have AT LEAST 2-3 attributes defined. DO NOT create entities without attributes." if is_er_question else ""}
        {"   - ⚠️ DO NOT repeat the same attribute multiple times within an entity - each attribute should appear only once per entity" if is_er_question else ""}
        {"   - ⚠️ Example CORRECT: 'Student entity has attributes: StudentID, Name, Address, PhoneNumbers' - has multiple attributes" if is_er_question else ""}
        {"   - ⚠️ Example WRONG: 'Student entity exists' - no attributes listed, will be REJECTED" if is_er_question else ""}
        {"   - ⚠️ ALL entities MUST be connected through relationships - NO standalone entities" if is_er_question else ""}
        {"   - ⚠️ ISA hierarchies MUST be subtype/supertype only (e.g., Student → GraduateStudent, NOT Student → Course)" if is_er_question else ""}
        {"   - At least ONE composite attribute (e.g., Address with Street, City, ZipCode)" if is_er_question else ""}
        {"   - At least ONE multivalued attribute (e.g., PhoneNumbers, EmailAddresses)" if is_er_question else ""}
        {"   - Descriptive attributes attached to relationships (e.g., EnrollmentDate on Enrolls relationship)" if is_er_question else ""}
        {"   - Relationships between entities with cardinality information" if is_er_question else ""}
        {"   - Real-world context (e.g., university, hospital, library, company)" if is_er_question else ""}
        {"   - ISA hierarchies (subtype/supertype relationships) with subtype-specific attributes" if is_er_question else ""}
        {"   - ⚠️ IMPORTANT: When describing child entities (subtypes), ONLY list the subtype-specific attributes. DO NOT include parent entity attributes - subtypes inherit them automatically." if is_er_question else ""}
        {"   " if is_er_question else ""}
        {"   After the diagram is generated, you MUST include a description section that explains:" if is_er_question else ""}
        {"   - The cardinality notation uses (min, max) approach (e.g., (1,1) for one-to-one, (1,N) for one-to-many)" if is_er_question else ""}
        {"   - Explanation of relationships and their cardinalities" if is_er_question else ""}
        {"   - Description of composite attributes, multivalued attributes, and descriptive attributes to relationships" if is_er_question else ""}
        {"   " if is_er_question else ""}
        {"   Then subquestions should: identify entities/attributes, identify relationships/cardinalities, draw ER/EER diagram (use [DIAGRAM PLACEHOLDER]), map to relational schema." if is_er_question else ""}
        
        {"6. **NORMALIZATION QUESTION REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if is_norm_question else ""}{"The question stem MUST include BOTH of the following:" if is_norm_question else ""}
        {"   - A relation schema with EXACTLY 5-6 attributes using ALPHABET LETTERS (A, B, C, D, E, F) in EXACT format: 'Consider a relation R(A, B, C, D, E) with...' OR 'Consider a relation R(A, B, C, D, E, F) with...'" if is_norm_question else ""}
        {"   - Functional dependencies in EXACT format using arrow notation: 'F = {{A->B, B->C, C->D}}' OR 'F = {{A->BC, B->D, C->EF, AC->G}}' OR 'F={{AB->C, B->D, C->E, DE->F}}'" if is_norm_question else ""}
        {"   - ⚠️ MANDATORY: Use ONLY alphabet letters (A, B, C, D, E, F, G) for attributes - DO NOT use real attribute names like StudentID, CourseCode, etc." if is_norm_question else ""}
        {"   - Format FDs to make key identification challenging and complex:" if is_norm_question else ""}
        {"     * Use composite determinants (e.g., AB->C, AC->G, DE->F)" if is_norm_question else ""}
        {"     * Use transitive dependencies (e.g., A->B, B->C, C->D)" if is_norm_question else ""}
        {"     * Use multiple attributes on right side (e.g., A->BC, C->EF)" if is_norm_question else ""}
        {"     * Make it difficult for students to easily figure out the key" if is_norm_question else ""}
        {"   " if is_norm_question else ""}
        {"   EXAMPLE OF CORRECT FORMAT (MANDATORY - USE THIS PATTERN):" if is_norm_question else ""}
        {"   'Consider a relation R(A, B, C, D, E, F) with the following set of functional dependencies F over R: F={{AB->C, B->D, CD->E, E->A, F->B}}'" if is_norm_question else ""}
        {"   OR:" if is_norm_question else ""}
        {"   'Consider a relation R(A, B, C, D, E) with the following set of functional dependencies over R: F={{AC->B, B->D, CD->E, E->A}}'" if is_norm_question else ""}
        {"   OR:" if is_norm_question else ""}
        {"   'Consider a relation R(A, B, C, D, E, F) with the following set of functional dependencies over R: F={{AB->CD, C->E, D->F, EF->A}}'" if is_norm_question else ""}
        {"   " if is_norm_question else ""}
        {"   ⚠️ CRITICAL REQUIREMENTS:" if is_norm_question else ""}
        {"   - MUST use alphabet letters (A, B, C, D, E, F) - NOT real attribute names" if is_norm_question else ""}
        {"   - MUST have exactly 5-6 attributes in the relation" if is_norm_question else ""}
        {"   - MUST use arrow notation (->) for functional dependencies" if is_norm_question else ""}
        {"   - ⚠️ MUST make FDs complex so students CANNOT easily figure out the key - use composite determinants (AB->C, AC->D), multiple attributes on right side (A->BC), and transitive dependencies that obscure the key" if is_norm_question else ""}
        {"   - ⚠️ AVOID simple patterns like A->B, B->C, C->D, A->E where A is obviously the key - instead use patterns like AB->C, B->D, CD->E where the key requires closure calculation" if is_norm_question else ""}
        {"   - ⚠️ DO NOT add extra descriptive text like 'In a company database' or 'attributes represent different aspects' - ONLY include the relation schema and functional dependencies" if is_norm_question else ""}
        {"   - WITHOUT A RELATION SCHEMA WITH 5-6 ALPHABET LETTER ATTRIBUTES AND FUNCTIONAL DEPENDENCIES IN THE STEM, THE QUESTION WILL BE REJECTED IMMEDIATELY." if is_norm_question else ""}
        {"   " if is_norm_question else ""}
        {"   ⚠️ VALID NORMALIZATION PROBLEM CONSTRAINTS (CRITICAL - MUST FOLLOW):" if is_norm_question else ""}
        {"   1. Candidate Key Requirement: The set of Functional Dependencies MUST allow for the identification of at least one Candidate Key." if is_norm_question else ""}
        {"      - Ensure that there exists at least one set of attributes whose closure covers all attributes in the relation" if is_norm_question else ""}
        {"      - Example: If R(A, B, C, D, E) with F={{A->B, B->C, C->D, D->E}}, then A is a candidate key (A+ = {A, B, C, D, E})" if is_norm_question else ""}
        {"   2. Transitive Dependency Requirement: Include at least one transitive dependency (e.g., X->Y and Y->Z) if testing 3NF." if is_norm_question else ""}
        {"      - This is essential for demonstrating 3NF violations" if is_norm_question else ""}
        {"      - Example: A->B, B->C creates a transitive dependency A->C (transitive through B)" if is_norm_question else ""}
        {"   3. Non-Circular FD Set: Ensure the FD set is not 'circular' unless specifically intended to have multiple candidate keys." if is_norm_question else ""}
        {"      - Avoid patterns like A->B, B->C, C->A unless you want multiple candidate keys" if is_norm_question else ""}
        {"      - If multiple candidate keys are intended, ensure they are clearly identifiable" if is_norm_question else ""}
        {"   4. Full Relation Schema: Always provide the complete relation schema R(A, B, C, D, E) so the universal set of attributes is explicitly known." if is_norm_question else ""}
        {"      - Format: 'Consider a relation R(A, B, C, D, E) with the following set of functional dependencies F over R: F={{...}}'" if is_norm_question else ""}
        {"      - All attributes in the relation must be listed explicitly" if is_norm_question else ""}
        {"   Then subquestions should ask for normalization steps to 3NF/BCNF and final decomposition." if is_norm_question else ""}
        
        {"6. **RELATIONAL ALGEBRA QUESTION REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if is_rel_algebra_question else ""}{"The question stem MUST include:" if is_rel_algebra_question else ""}
        {"   - A scenario description (2-3 sentences) explaining the database context" if is_rel_algebra_question else ""}
        {"   - ALL relations with their attributes listed explicitly in the format: 'relation_name (attr1, attr2, attr3)'" if is_rel_algebra_question else ""}
        {"   - Each relation must be on a separate line for clarity" if is_rel_algebra_question else ""}
        {"   " if is_rel_algebra_question else ""}
        {"7. **Q4 SCHEMA REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   The question stem MUST include a COMPREHENSIVE database schema in the EXACT format from past papers:" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Format: 'Consider the following schema of a database designed for a [Domain]: Table1 (primaryKey: type, attr2: type, attr3: type) Table2 (primaryKey: type, attr2: type, attr3: type) ...'" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Primary keys MUST be the FIRST attribute in each table (e.g., bookId, memberId, loanId)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Primary keys should be indicated (in PDF they are underlined, in text they are the first attribute)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - ALL attributes MUST include data types (e.g., int, varchar(50), date, real)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Include 3-5 tables with meaningful relationships. You can use ANY domain: Library (Book, Member, Loan, Fine), Hospital (Patient, Doctor, Appointment), University (Student, Course, Enrollment), School (Student, Teacher, Class), E-commerce (Product, Order, Customer), Airline (Flight, Passenger, Booking), etc." if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - ⚠️🚨 CRITICAL ATTRIBUTE REQUIREMENT (MANDATORY - ZERO TOLERANCE):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Each table MUST have AT LEAST 3-4 attributes total (primary key + 2-3 other attributes)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Tables with ONLY 2 attributes (primary key + 1 other) will be AUTOMATICALLY REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Tables with ONLY 1 attribute (just primary key) will be AUTOMATICALLY REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * ⚠️ BEFORE OUTPUTTING: Count attributes in EACH table - if any table has < 3 attributes, ADD MORE ATTRIBUTES" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - ✅ CORRECT EXAMPLES (MUST FOLLOW THIS PATTERN):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Patient (patientId: int, name: varchar(100), address: varchar(150), dob: date) - 4 attributes ✅" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Book (bookId: int, title: varchar(100), author: varchar(50), isbn: varchar(20), publicationYear: int) - 5 attributes ✅" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Student (studentId: int, name: varchar(100), email: varchar(50), phone: varchar(15)) - 4 attributes ✅" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - ❌ WRONG EXAMPLES (WILL BE REJECTED):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Patient (patientId: int, name: varchar(100)) - only 2 attributes ❌ REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Book (bookId: int) - only 1 attribute ❌ REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Student (studentId: int, name: varchar(100)) - only 2 attributes ❌ REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - After the schema, include a description of each table explaining what it stores" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Example format: 'The 'Book' table stores information about books available in the library, including unique book ID, title, author, ISBN, publication year, genre, and the number of available copies.'" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - DO NOT use simple format like 'Given a database with tables: Customers (id, name, email)' - use full schema with data types" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   EXAMPLE OF CORRECT FORMAT (with newlines between each line):" if is_rel_algebra_question else ""}
        {"   'Consider the following relational database schema containing airline flight information." if is_rel_algebra_question else ""}
        {"   Here the passenger relation gives the details of the passengers who book flights." if is_rel_algebra_question else ""}
        {"   The agency relation keeps the details of agents who book flights for passengers." if is_rel_algebra_question else ""}
        {"   The flight relation stores the details of each available flight." if is_rel_algebra_question else ""}
        {"   The booking relation stores required booking details." if is_rel_algebra_question else ""}
        {"   " if is_rel_algebra_question else ""}
        {"   passenger (pid, pname, pgender, pcity)" if is_rel_algebra_question else ""}
        {"   agency (aid, aname, acity)" if is_rel_algebra_question else ""}
        {"   flight (fid, fdate, time, departs, arrives)" if is_rel_algebra_question else ""}
        {"   booking (pid, aid, fid, fdate)'" if is_rel_algebra_question else ""}
        {"   " if is_rel_algebra_question else ""}
        {"   IMPORTANT: Use actual newline characters between each sentence and relation definition, NOT spaces." if is_rel_algebra_question else ""}
        {"   " if is_rel_algebra_question else ""}
        {"   ⚠️ WITHOUT A COMPLETE RELATIONAL SCHEMA WITH ALL RELATIONS AND ATTRIBUTES LISTED, THE QUESTION WILL BE REJECTED IMMEDIATELY." if is_rel_algebra_question else ""}
        {"   Then subquestions should ask for relational algebra expressions or tuple calculus based on this schema." if is_rel_algebra_question else ""}
        
        ⚠️ CRITICAL: INSTRUCTION PATTERN PRESERVATION (MANDATORY - ZERO TOLERANCE) ⚠️
        The structure above includes "Instruction Pattern" text for each part. These patterns are from historical exam papers and MUST be preserved EXACTLY.
        
        **HOW TO USE INSTRUCTION PATTERNS (STRICT RULES):**
        1. For each sub-question, look at the "Instruction Pattern" provided in the structure above
        2. Copy the EXACT instruction wording from the pattern - DO NOT change task verbs, qualifiers, or instruction structure
        3. **"Briefly explain" RULE (CRITICAL)**: 
           - If pattern says "Briefly explain", you MUST write "Briefly explain" (NOT "explain", "Explain", "briefly explain", or any variation)
           - The word "Briefly" MUST be included exactly as shown
           - Missing "Briefly" will cause IMMEDIATE REJECTION
           - Example: Pattern "Briefly explain how authentication works" → Output MUST be "Briefly explain how authentication works" (with "Briefly")
        4. **"Accept or refute" RULE**: 
           - If pattern says "Accept or refute", you MUST write "Accept or refute" (NOT "accept or reject", "accept or deny", or similar)
           - Preserve EXACT wording
        5. **"Write a T-SQL statement" RULE**: 
           - If pattern says "Write a T-SQL statement", you MUST write "Write a T-SQL statement" (NOT "Write a SQL query", "Create a T-SQL", "Write T-SQL", etc.)
           - Preserve the exact phrase "Write a T-SQL statement"
        6. **JDBC API RULE**: 
           - If pattern mentions JDBC API, Type 2 Driver, or Java database connectivity, these are VALID database topics
           - Preserve these topics exactly as they appear in the pattern
        7. {"**Q4 SCHEMA CONSISTENCY RULE (CRITICAL - OVERRIDES PATTERN PRESERVATION)**: " if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else "ONLY change scenario-specific details (person names, organization names, database names, entity names, relation names)"}
           {"   - ⚠️ FOR Q4 ONLY: ALL subquestions (parts a, b, c) MUST reference ONLY the tables/entities YOU define in YOUR schema above" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
           {"   - ⚠️ You can use ANY domain: Library (Book, Member, Loan, Fine), Hospital (Patient, Doctor, Appointment), University (Student, Course, Enrollment), School (Student, Teacher, Class), E-commerce (Product, Order, Customer), Airline (Flight, Passenger, Booking), etc." if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
           {"   - ⚠️ Template patterns use library domain (Member, Fine) - you MUST adapt ALL references to match YOUR chosen domain" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
           {"   - ⚠️ Example adaptations: 'Member' → 'Patient' (hospital) or 'Student' (university); 'Fine' → 'Appointment' (hospital) or 'Enrollment' (university); 'TotalFineAmount' → 'TotalAppointmentAmount' (hospital) or 'TotalEnrollmentFee' (university)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
           {"   - ⚠️ Adapt concepts too: 'fines' → 'appointment fees' (hospital) or 'course fees' (university); 'overdue' → 'missed' (hospital) or 'late enrollment' (university)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
           {"   - ⚠️ Template patterns are GUIDES - you MUST adapt table names, column names, concepts, and entities to match YOUR schema domain" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
           {"   - ⚠️ VIOLATION: If you generate ANY schema but parts (b) and (c) reference tables/concepts from a different domain, the question will be REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        8. Keep ALL task verbs, qualifiers ("Briefly", "Assuming", etc.), and instruction structure EXACTLY as shown
        
        **VALIDATION CHECKLIST (Before outputting):**
        - [ ] Every "Briefly explain" in pattern has "Briefly" in output
        - [ ] Every "Accept or refute" in pattern is preserved exactly
        - [ ] Every "Write a T-SQL statement" in pattern is preserved exactly
        - [ ] All qualifiers and task verbs match the pattern exactly
        - [ ] Only scenario details (names, places) have changed
        
        **EXAMPLES OF CORRECT PATTERN PRESERVATION:**
        - If pattern says: "Briefly explain how authentication and authorization are achieved in SQL Server"
          → Your output: "Briefly explain how authentication and authorization are achieved in SQL Server" (EXACT SAME)
        
        - If pattern says: "Accept or refute the above statement justifying your answer"
          → Your output: "Accept or refute the above statement justifying your answer" (EXACT SAME)
        
        - If pattern says: "Write a T-SQL statement to create a login to Sarah with windows authentication"
          → Your output: "Write a T-SQL statement to create a login to [DIFFERENT_NAME] with windows authentication"
          → Change "Sarah" to a different name, but keep "Write a T-SQL statement to create a login to" and "with windows authentication" EXACTLY
        
        - If pattern has a long scenario (e.g., "A financial institution... Sarah is the senior DBA... Write a T-SQL statement to create a login to Sarah"):
          → Change: "financial institution" → "healthcare facility", "Sarah" → "John", "client accounts" → "patient records"
          → Keep: The entire instruction structure "Write a T-SQL statement to create a login to [person] with windows authentication" EXACTLY
        
        **RULES:**
        - Keep qualifiers like "Briefly" - if pattern says "Briefly explain", you MUST say "Briefly explain" (NOT "explain")
        - Keep exact phrases like "Accept or refute the above statement justifying your answer" - preserve EXACTLY
        - Keep exact T-SQL instruction patterns - preserve structure, only change names/contexts
        - For long scenarios, preserve scenario structure but change: person names, organization names, database names, department names
        - ONLY change scenario/context details - NEVER change instruction wording, task verbs, or structure
        - **Historical Pattern Alignment**: Follow the exact structure, style, and difficulty level of past exam questions
        - **Syllabus Compliance**: Ensure all content aligns with Database Management Systems curriculum modules
        - **Past Paper Reflection**: Questions must reflect topics and patterns from historical exam papers
        - **Bloom's Taxonomy**: Ensure a mix of Recall (Define/List) and Application (Design/Analyze) as seen in past papers
        - **Single Scenario**: Use ONE cohesive scenario for all parts.
        - **Authenticity**: Write a real, solvable problem with specific details matching past paper style
        - **Database Systems Only**: All content must be relevant to Database Management Systems - NO exceptions
        - **No Deviation**: Do NOT introduce concepts, topics, or approaches not found in past papers or syllabus
        
        


        OUTPUT JSON FORMAT (STRICT SCHEMA):
        {{
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "text": "Question stem text here (minimum 50 characters). This is the main scenario/context for all subquestions. {er_context}",
            "subquestions": [
                {{ "label": "a", "text": "Complete question text here (minimum 20 characters, no placeholders)", "marks": 5 }}
            ]
        }}
        
        REMEMBER:
        - Every "text" field must be at least 20 characters and contain no placeholders.
        - Marks must sum exactly to {slot.get('target_marks')}.
        - All subquestions must be semantically distinct.
        """
        
        # Add schema consistency rule for Q4 SQL questions
        if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower():
            prompt += (
                "\n\n"
                "⚠️ CRITICAL SCHEMA CONSISTENCY RULE FOR Q4:\n"
                "ALL subquestions (parts a, b, c) MUST reference ONLY the tables/entities you define in the schema above.\n"
                "- You can use ANY domain: Library (Book, Member, Loan, Fine), Hospital (Patient, Doctor, Appointment), University (Student, Course, Enrollment), School (Student, Teacher, Class), E-commerce (Product, Order, Customer), Airline (Flight, Passenger, Booking), etc.\n"
                "- Template patterns use library domain (Member, Fine) - you MUST adapt ALL references to match YOUR chosen domain.\n"
                "- Adapt table names: 'Member' → 'Patient' (hospital) or 'Student' (university); 'Fine' → 'Appointment' (hospital) or 'Enrollment' (university).\n"
                "- Adapt column names: 'TotalFineAmount' → 'TotalAppointmentAmount' (hospital) or 'TotalEnrollmentFee' (university).\n"
                "- Adapt concepts: 'fines' → 'appointment fees' (hospital) or 'course fees' (university); 'overdue' → 'missed' (hospital) or 'late enrollment' (university).\n"
                "- Example: If template says 'Members' table but you generated 'Patients' table, change 'Members' to 'Patients' AND adapt concepts (fines → appointment fees).\n"
                "- Example: If template says 'Fine' table but you generated 'Appointment' table, adapt the function/trigger to work with 'Appointment' AND adapt column names ('TotalFineAmount' → 'TotalAppointmentAmount').\n"
                "⚠️ VIOLATION OF THIS RULE WILL CAUSE IMMEDIATE REJECTION.\n"
            )
        
        if feedback:
            prompt += f"\n\nCRITIC FEEDBACK FROM PREVIOUS ATTEMPT (YOU MUST FIX THESE):\n{feedback}\n"
            
        return prompt

    
    def _build_paraphrase_prompt(self, slot, template, context, global_context, feedback=None, *, banned_topics=None) -> str:
        q_no = slot.get("question_no") or slot.get("slot_id", "")
        """Mode 2: Paraphrasing (Keep structure, change content)."""
        pattern_label = template.get('pattern_label', '').lower()
        is_er_question = "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label or "schema" in pattern_label
        is_norm_question = "normalization" in pattern_label or "normal form" in pattern_label
        
        # Get required structure and count
        structure_fingerprint = template.get("required_structure") or [{"label": "a", "marks": slot.get("target_marks")}]
        
        # Build structure string with text patterns if available
        structure_parts = []
        instruction_patterns = []  # Store patterns for explicit enforcement
        for s in structure_fingerprint:
            label = s.get('label', '?')
            marks = s.get('marks', 0)
            text_pattern = s.get('text', '')  # Get stored text pattern
            if text_pattern:
                # Clean text pattern (remove label prefix if present)
                clean_pattern = text_pattern.strip()
                if clean_pattern and len(clean_pattern) > 2 and clean_pattern[1] in [')', '.', '?']:
                    clean_pattern = clean_pattern[2:].strip()
                
                # For SQL_DDL_DML questions, if pattern starts with "Find", convert to "Write SQL queries"
                pattern_label_lower = template.get('pattern_label', '').lower()
                if "sql" in pattern_label_lower and clean_pattern.lower().startswith("find"):
                    # Extract the query requirement part
                    if "find" in clean_pattern.lower():
                        # Convert "Find X" to "Write SQL queries to find X"
                        query_part = clean_pattern.split("Find", 1)[1].strip() if "Find" in clean_pattern else clean_pattern.split("find", 1)[1].strip()
                        clean_pattern = f"Write SQL queries to find {query_part}"
                
                instruction_patterns.append(clean_pattern)
                # Include the instruction pattern for preservation
                structure_parts.append(f"- Part {label}: {marks} marks\n  Instruction Pattern (MUST PRESERVE EXACTLY): \"{clean_pattern}\"")
            else:
                structure_parts.append(f"- Part {label}: {marks} marks")
                instruction_patterns.append("")
        structure_str = "\n".join(structure_parts)
        required_count = len(structure_fingerprint)

        er_context = ""
        if is_er_question:
             er_context = "Include a scenario describing entities, relationships, and attributes."
        elif is_norm_question:
             er_context = "Include a relation schema and functional dependencies."
        else:
             er_context = "Include relevant context and background information."
        
        base_prompt = f"""
        Generate ONE high-quality university exam question for a Database Systems course.
        
        ⚠️ CRITICAL: SYLLABUS ALIGNMENT REQUIREMENTS ⚠️
        - Generate questions STRICTLY based on historical exam patterns from past papers
        - All questions MUST be directly aligned with past exam content and curriculum requirements
        - Ensure questions reflect ONLY core Database Management Systems syllabus content
        - Follow the exact structure and style of historical exam questions
        - Do NOT introduce topics unrelated to the core syllabus or past paper patterns
        
        🚫 STRICT NON-DATABASE TOPIC PROHIBITION 🚫
        ABSOLUTELY DO NOT include any topics from:
        - Networking: TCP/IP, routing, switching, packets, datagrams, OSI model, network layers, sockets, DNS, DHCP, VPN, firewall
        - Operating Systems: CPU scheduling, process scheduling, memory management, file systems, semaphores, mutexes, threads, processes
        - Web Development: HTML, CSS, JavaScript, frontend, backend, web development
        - Compiler Design: Compiler, interpreter, syntax, parsing, lexical analysis
        - Software Engineering: Agile, Scrum, Waterfall, SDLC, software engineering methodologies
        - Machine Learning & AI: Neural networks, deep learning, machine learning, AI algorithms
        - Any other topics NOT in Database Management Systems curriculum
        
        ALL questions MUST remain within Database Management Systems (DMS) scope ONLY.
        
        TASK:
        You are given a 'Reference Question' from a past paper.
        Your goal is to WRITE A NEW QUESTION that has the EXACT SAME STRUCTURE and DIFFICULTY, but applies to a COMPLETELY DIFFERENT SCENARIO.
        
        REFERENCE QUESTION (Historical Pattern):
        {template.get('full_text', '')}
        
        REQUIRED STRUCTURE (MANDATORY - NO EXCEPTIONS):
{structure_str}
        
        ⚠️ CRITICAL: You MUST generate EXACTLY {required_count} sub-questions matching this structure.
        - If template shows 9 parts, you MUST generate 9 sub-questions
        - If template shows 7 parts, you MUST generate 7 sub-questions
        - Any other count will be REJECTED immediately
        - The number of sub-questions MUST match the template structure EXACTLY
        
        CONSTRAINTS:
        1. **Keep Structure EXACTLY**: You MUST generate EXACTLY {required_count} sub-questions matching the structure above. If template shows 9 parts, generate 9. If 7 parts, generate 7. NO DEVIATION.
        2. **PRESERVE INSTRUCTION PATTERNS** (CRITICAL - ZERO TOLERANCE): 
           The structure above shows "Instruction Pattern (MUST PRESERVE EXACTLY)" for each part. These are from historical exam papers.
           
           **FOR EACH SUB-QUESTION:**
           - Look at the "Instruction Pattern" provided in the structure above
           - Copy the EXACT instruction wording from that pattern
           {"   - ⚠️ **Q4 SCHEMA CONSISTENCY (CRITICAL - OVERRIDES PATTERN PRESERVATION)**: For Q4 ONLY, ALL subquestions MUST reference ONLY the tables/entities YOU define in YOUR schema. You can use ANY domain (Library, Hospital, University, School, E-commerce, Airline, etc.). Template patterns use library domain - adapt table names ('Member' → 'Patient'/'Student'), column names ('TotalFineAmount' → domain-appropriate), and concepts ('fines' → domain-appropriate) to match YOUR schema." if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else "   - ONLY change scenario-specific details (person names, organization names, database names, entity names, relation names)"}
           - Keep ALL task verbs, qualifiers, and instruction structure EXACTLY as shown
           
           **EXAMPLES:**
           - Pattern: "Briefly explain how authentication and authorization are achieved in SQL Server"
             → Output: "Briefly explain how authentication and authorization are achieved in SQL Server" (EXACT SAME)
           
           - Pattern: "Accept or refute the above statement justifying your answer"
             → Output: "Accept or refute the above statement justifying your answer" (EXACT SAME)
           
           - Pattern: "Write a T-SQL statement to create a login to Sarah with windows authentication"
             → Output: "Write a T-SQL statement to create a login to [DIFFERENT_NAME] with windows authentication"
             → Change "Sarah" to different name, keep rest EXACTLY
           
           - Pattern with long scenario: "A financial institution... Sarah is the senior DBA... Write a T-SQL statement to create a login to Sarah"
             → Change: "financial institution" → "healthcare facility", "Sarah" → "John", "client accounts" → "patient records"
             → Keep: "Write a T-SQL statement to create a login to [person] with windows authentication" EXACTLY
           
           **HANDLING LONG SCENARIOS** (e.g., Q3 part 'e' with 100+ words):
           - Preserve the EXACT instruction pattern at the end
           - Change person names, organization types, database names, department names
           - Keep the same role structure and relationships
           - Keep the same instruction wording EXACTLY
        3. **Historical Pattern Alignment**: Maintain the exact structure, style, and difficulty level of the reference question
        4. **Syllabus Compliance**: Ensure all content aligns with Database Management Systems curriculum modules
        5. **Change Scenario**: If original is about a Bank, you write about a Library or Hospital (completely different scenario).
        6. **NO PLAGIARISM**: Do not copy the text verbatim. Re-invent the scenario and context, but keep the instruction pattern.
        7. **No Deviation**: Do NOT introduce concepts, topics, or approaches not found in past papers or syllabus
        
        Specifications:
        - Question Number: {slot.get('question_no') or slot.get('slot_id') or "Q?"}
        - Total Marks: {slot.get('target_marks')}
        - Historical Pattern: This template is derived from past exam papers - follow its structure EXACTLY
        - Topic Context: {context[:500]}...

        TOOLING RULES (STRICT):
        - Do NOT output Mermaid, Graphviz, Kroki links, or any external-diagram syntax.
        - Do NOT include code fences like ```mermaid.
        - If a diagram would normally be required, phrase it as a normal exam instruction in plain text (e.g., "Draw an ER diagram...") without any generated diagram code.

        TOPIC UNIQUENESS (STRICT):
        - This question's topic MUST be: {template.get('pattern_label', '')}
        - This topic is derived from historical exam patterns - maintain alignment
        - BANNED TOPICS (must NOT be used): {banned_topics or []}
        
        GLOBAL UNIQUENESS (DO NOT REUSE THESE):
        - BANNED TOPICS (MUST NOT REPEAT): {global_context.get('banned_topics', [])} (You MUST use a DIFFERENT topic - each question must have a unique topic)
        - Topics already used: {global_context.get('used_topics', [])}
        - USED QUESTION TYPES: {global_context.get('used_question_types', [])}
        - PREVIOUS SCENARIOS (DO NOT REUSE): {global_context.get('used_scenarios', [])}
        
        CRITICAL CONTENT RULES (ZERO TOLERANCE - VIOLATIONS WILL CAUSE REJECTION):
        1. **SYLLABUS ALIGNMENT**: Questions MUST strictly reflect historical exam patterns and syllabus content. NO deviation.
        2. **NO NON-DATABASE TOPICS**: ABSOLUTELY DO NOT include networking, OS, web development, compiler design, software engineering, or ML/AI topics.
        3. **HISTORICAL PATTERN COMPLIANCE**: Follow the exact structure, style, and difficulty level of past exam questions.
        4. **NO PLACEHOLDERS**: Never use "...", "TBD", "[insert", "[placeholder", or any placeholder text. Every field must have complete, valid content.
        5. **MARKS MUST SUM EXACTLY**: Sub-question marks must sum to exactly {slot.get('target_marks')}. Double-check your math.
        6. **EACH SUBQUESTION MUST BE SEMANTICALLY DISTINCT**: Use different task verbs/intents. No duplicate or near-duplicate questions.
        7. **NO "DESCRIBED ABOVE" REFERENCES**: Never say "described above", "as shown above" unless you have already included the described content.
        8. **SINGLE SCENARIO ENFORCEMENT**: If this question involves a scenario, it must be the ONLY scenario used for the ENTIRE question (all sub-questions). DO NOT mix multiple scenarios.
        9. **NO MCQs**: This is a structural paper. DO NOT generate Multiple Choice Questions. All questions must be descriptive or design-based.
        10. **NO FIGURE REFERENCES**: Do NOT refer to "Figure 1", "Slide 2", etc.
        11. **NO EMPTY QUESTIONS**: Every sub-question `text` field must have substantial content (minimum 20 characters).
        12. **NO DEVIATION**: Do NOT introduce concepts, topics, or approaches not found in past papers or syllabus.
        
        {"9. **ER/EER QUESTION REQUIREMENTS**: " if is_er_question else ""}{"The question stem MUST include a scenario block (2-5 sentences) describing entities, relationships, and attributes. Then subquestions should: identify entities/attributes, identify relationships/cardinalities, draw ER/EER diagram (use [DIAGRAM PLACEHOLDER]), map to relational schema." if is_er_question else ""}
        
        {"9. **NORMALIZATION QUESTION REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if is_norm_question else ""}{"The question stem MUST include BOTH:" if is_norm_question else ""}
        {"   - A relation schema with EXACTLY 5-6 attributes using ALPHABET LETTERS (A, B, C, D, E, F) in EXACT format: 'Consider a relation R(A, B, C, D, E) with...' OR 'Consider a relation R(A, B, C, D, E, F) with...'" if is_norm_question else ""}
        {"   - Functional dependencies in EXACT format using arrow notation: 'F = {{A->BC, B->D, C->EF, AC->G}}' OR 'F={{AB->C, B->D, C->E, DE->F}}'" if is_norm_question else ""}
        {"   - ⚠️ MANDATORY: Use ONLY alphabet letters (A, B, C, D, E, F, G) for attributes - DO NOT use real attribute names" if is_norm_question else ""}
        {"   - Format FDs to make key identification challenging: use composite determinants (AB->C), transitive dependencies (A->B, B->C), multiple attributes on right side (A->BC)" if is_norm_question else ""}
        {"   ⚠️ CRITICAL: WITHOUT A RELATION SCHEMA WITH 5-6 ALPHABET LETTER ATTRIBUTES AND COMPLEX FUNCTIONAL DEPENDENCIES IN THE STEM, THE QUESTION WILL BE REJECTED IMMEDIATELY." if is_norm_question else ""}
        {"   Then subquestions should ask for normalization steps to 3NF/BCNF and final decomposition." if is_norm_question else ""}
        
        {"10. **Q4 SCHEMA REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   The question stem MUST include a COMPREHENSIVE database schema in the EXACT format from past papers:" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Format: 'Consider the following schema of a database designed for a [Domain]: Table1 (primaryKey: type, attr2: type, attr3: type) Table2 (primaryKey: type, attr2: type, attr3: type) ...'" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Primary keys MUST be the FIRST attribute in each table (e.g., bookId, memberId, loanId) - these are underlined in PDF" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - ALL attributes MUST include data types (e.g., int, varchar(50), date, real)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - Include 3-5 tables with meaningful relationships. You can use ANY domain: Library (Book, Member, Loan, Fine), Hospital (Patient, Doctor, Appointment), University (Student, Course, Enrollment), School (Student, Teacher, Class), E-commerce (Product, Order, Customer), Airline (Flight, Passenger, Booking), etc." if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - After the schema, include a description of each table explaining what it stores" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - EXAMPLE FROM PAST PAPER (MUST FOLLOW THIS EXACT FORMAT - NO DEVIATIONS):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   Format: 'Consider the following schema of a database designed for a [ACTUAL_DOMAIN_NAME]: Table1 (primaryKeyId: int, attr2: varchar(50), attr3: date) Table2 (primaryKeyId: int, attr2: varchar(50)) ... The Table1 table stores information about [description]. The Table2 table holds details about [description].'" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - CRITICAL REQUIREMENTS:" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Replace [ACTUAL_DOMAIN_NAME] with real domain (Library, Hospital, University, School, E-commerce, Airline, etc.) - DO NOT leave [Domain] placeholder" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Every table MUST have primary key as FIRST attribute (e.g., bookId: int, memberId: int)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Every attribute MUST have data type (int, varchar(50), date, real, etc.)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * MUST have 3-5 tables (not 2, not 6)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * ⚠️🚨 CRITICAL ATTRIBUTE REQUIREMENT (MANDATORY - ZERO TOLERANCE):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Each table MUST have AT LEAST 3-4 attributes total (primary key + 2-3 other attributes)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Tables with ONLY 2 attributes (primary key + 1 other) will be AUTOMATICALLY REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Tables with ONLY 1 attribute (just primary key) will be AUTOMATICALLY REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - ⚠️ BEFORE OUTPUTTING: Count attributes in EACH table - if any table has < 3 attributes, ADD MORE ATTRIBUTES" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * ✅ CORRECT EXAMPLES (MUST FOLLOW THIS PATTERN):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Patient (patientId: int, name: varchar(100), address: varchar(150), dob: date) - 4 attributes ✅" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Book (bookId: int, title: varchar(100), author: varchar(50), isbn: varchar(20), publicationYear: int) - 5 attributes ✅" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Student (studentId: int, name: varchar(100), email: varchar(50), phone: varchar(15)) - 4 attributes ✅" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * ❌ WRONG EXAMPLES (WILL BE REJECTED):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Patient (patientId: int, name: varchar(100)) - only 2 attributes ❌ REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Book (bookId: int) - only 1 attribute ❌ REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"       - Student (studentId: int, name: varchar(100)) - only 2 attributes ❌ REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * MUST include description for EACH table after schema (format: The TableName table stores/holds/manages...)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - DO NOT use simple format like 'Given a database with tables: Customers (id, name, email)' - use full schema with data types" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"   - ⚠️ CRITICAL Q4 STRUCTURE REQUIREMENT (MANDATORY):" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Part (a) MUST have nested subquestions (i, ii, iii)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Part (a) parent text: 'Write SQL Queries to perform the following: i. Find [something]...'" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Part (a) nested item (ii): MUST be a SQL query starting with 'Find' (e.g., 'Find the [entity] who has...' or 'Find the [attributes] of [entities]...')" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Part (a) nested item (iii): MUST be a SQL query starting with 'Find' (e.g., 'Find the [attributes] of [entities]...')" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Part (b): MUST be 'Create a function to calculate...' (NOT in part (a) nested items)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * Part (c): MUST be 'Create a trigger that automatically updates...' (NOT in part (a) nested items)" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * ⚠️ VIOLATION: If part (a) nested items (ii, iii) contain 'Create a function' or 'Create a trigger', the question will be REJECTED" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        {"     * ⚠️ CORRECT STRUCTURE: Part (a) nested items = SQL queries (Find), Part (b) = Function, Part (c) = Trigger" if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower() else ""}
        
        Output valid JSON (STRICT SCHEMA):
        {{
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "text": "Question stem text here (minimum 50 characters). This is the main scenario/context for all subquestions. {er_context}",
            "subquestions": [
                {{
                    "label": "a",
                    "text": "Complete question text here (minimum 20 characters, no placeholders)",
                    "marks": 5
                }}
            ]
        }}

        REMEMBER:
        - Every "text" field must be at least 20 characters and contain no placeholders.
        - Marks must sum exactly to {slot.get('target_marks')}.
        - All subquestions must be semantically distinct.
        """

        # Add schema consistency rule for Q4 SQL questions
        if q_no and q_no in ["Q4", "4"] and "sql" in pattern_label.lower():
            base_prompt += (
                "\n\n"
                "🚨 CRITICAL SCHEMA CONSISTENCY RULE FOR Q4 (MANDATORY - ZERO TOLERANCE):\n"
                "ALL subquestions (parts a, b, c) MUST reference ONLY the tables/entities you define in YOUR schema above.\n"
                "\n"
                "⚠️ CRITICAL RULES:\n"
                "1. **SCHEMA FIRST**: Before writing parts (b) and (c), look at YOUR schema in part (a) and identify ALL table names.\n"
                "2. **NO CROSS-DOMAIN REFERENCES**: If your schema uses Hospital domain (Patient, Doctor, Appointment), parts (b) and (c) MUST use ONLY these tables.\n"
                "3. **NO TEMPLATE TABLES**: Template patterns mention 'Member', 'Fine', 'Book' - these are EXAMPLES only. You MUST use YOUR schema tables.\n"
                "4. **FUNCTION/TRIGGER CONSISTENCY**: Parts (b) and (c) functions/triggers MUST work with YOUR schema tables, not template tables.\n"
                "\n"
                "✅ CORRECT EXAMPLES:\n"
                "- Schema: Hospital (Patient, Doctor, Appointment) → Part (b): 'Create a function to calculate total appointment amount for a patient'\n"
                "- Schema: University (Student, Course, Enrollment) → Part (c): 'Create a trigger to update student enrollment count'\n"
                "- Schema: Library (Book, Member, Loan) → Part (b): 'Create a function to calculate total fine amount for a member'\n"
                "\n"
                "❌ WRONG EXAMPLES (WILL BE REJECTED):\n"
                "- Schema: Hospital (Patient, Doctor) → Part (b): 'Create a function for Members table' ❌ (Member not in schema)\n"
                "- Schema: University (Student, Course) → Part (c): 'Create a trigger on Fine table' ❌ (Fine not in schema)\n"
                "- Schema: Hospital → Part (b): References 'Book' or 'Loan' tables ❌ (Wrong domain)\n"
                "\n"
                "🔍 VALIDATION CHECKLIST:\n"
                "- [ ] Part (b) function references ONLY tables from YOUR schema\n"
                "- [ ] Part (c) trigger references ONLY tables from YOUR schema\n"
                "- [ ] No mention of 'Member', 'Fine', 'Book', 'Loan' unless they are in YOUR schema\n"
                "- [ ] Column names match YOUR schema (e.g., if schema has 'appointmentAmount', use that, not 'fineAmount')\n"
                "\n"
                "⚠️ VIOLATION OF THIS RULE WILL CAUSE IMMEDIATE REJECTION BY THE CRITIC.\n"
            )

        if feedback:
            base_prompt += f"\n\nCRITIC FEEDBACK FROM PREVIOUS ATTEMPT (YOU MUST FIX THESE ERRORS):\n{feedback}\n"
            
        return base_prompt
