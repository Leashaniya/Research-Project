import json
from app.core.config import settings
from app.core.llm_factory import get_llm_client
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
                    parsed["subquestions"] = self._enforce_instruction_patterns(
                        parsed["subquestions"],
                        required_structure
                    )
                
                # Normalize marks to ensure they sum correctly
                parsed["subquestions"] = self._normalize_subquestion_marks(
                    parsed["subquestions"], 
                    target_marks
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

    def _normalize_subquestion_marks(self, subquestions: list, target_marks: int) -> list:
        """
        Normalize subquestion marks to ensure they sum exactly to target_marks.
        Uses proportional distribution based on relative weightage.
        
        Args:
            subquestions: List of subquestion dicts with 'marks' field
            target_marks: Target total marks for all subquestions
            
        Returns:
            List of subquestions with normalized marks that sum to target_marks
        """
        if not subquestions or target_marks <= 0:
            return subquestions
        
        # Get current marks (default to 0 if missing)
        current_marks = [int(sq.get("marks", 0)) for sq in subquestions]
        current_sum = sum(current_marks)
        
        # If sum is already correct, return as-is
        if current_sum == target_marks:
            return subquestions
        
        # If all marks are 0 or invalid, distribute evenly
        if current_sum == 0 or all(m == 0 for m in current_marks):
            marks_per_subq = target_marks // len(subquestions)
            remainder = target_marks % len(subquestions)
            normalized = []
            for idx, sq in enumerate(subquestions):
                marks = marks_per_subq + (1 if idx < remainder else 0)
                normalized.append({**sq, "marks": marks})
            return normalized
        
        # Proportional distribution: scale each mark by the ratio
        ratio = target_marks / current_sum
        normalized_marks = [int(round(m * ratio)) for m in current_marks]
        
        # Fix rounding errors: ensure sum equals target_marks exactly
        normalized_sum = sum(normalized_marks)
        diff = target_marks - normalized_sum
        
        if diff != 0:
            # Distribute the difference to the largest subquestions first
            # This preserves the relative weightage better
            sorted_indices = sorted(
                range(len(normalized_marks)), 
                key=lambda i: normalized_marks[i], 
                reverse=True
            )
            
            # Add/subtract the difference
            for i in sorted_indices:
                if diff == 0:
                    break
                if diff > 0:
                    normalized_marks[i] += 1
                    diff -= 1
                else:
                    if normalized_marks[i] > 1:  # Don't go below 1
                        normalized_marks[i] -= 1
                        diff += 1
        
        # Update subquestions with normalized marks
        normalized = []
        for idx, sq in enumerate(subquestions):
            normalized.append({**sq, "marks": normalized_marks[idx]})
        
        # Final verification
        final_sum = sum(sq["marks"] for sq in normalized)
        if final_sum != target_marks:
            # Last resort: adjust the last subquestion
            if normalized:
                normalized[-1]["marks"] = target_marks - sum(sq["marks"] for sq in normalized[:-1])
                # Ensure it's at least 1
                if normalized[-1]["marks"] < 1:
                    normalized[-1]["marks"] = 1
                    # Adjust another subquestion
                    for sq in normalized[:-1]:
                        if sq["marks"] > 1:
                            sq["marks"] -= 1
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

    def _enforce_instruction_patterns(self, subquestions: list, required_structure: list) -> list:
        """
        Enforce instruction patterns from template if LLM deviated.
        For each sub-question, if template has a text pattern, ensure the generated text preserves it.
        """
        if not required_structure or len(required_structure) != len(subquestions):
            return subquestions
        
        enforced = []
        for idx, (sq, struct_item) in enumerate(zip(subquestions, required_structure)):
            template_text = struct_item.get("text", "").strip()
            
            # If template has text pattern, check if we should enforce it
            if template_text and len(template_text) > 10:
                # Clean template text (remove label prefix)
                clean_template = template_text
                if clean_template and len(clean_template) > 2 and clean_template[1] in [')', '.', '?']:
                    clean_template = clean_template[2:].strip()
                
                # Extract instruction pattern (the task/instruction part, not the scenario)
                # For patterns like "Briefly explain...", "Write a T-SQL statement...", "Accept or refute..."
                # We want to preserve these exact phrases
                generated_text = sq.get("text", "").strip()
                
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
            
            enforced.append(sq)
        
        return enforced

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
        import re
        
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
                
                # Generate appropriate SQL code based on question context
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
                            updated_text = original_text
                            # Ensure the question references the code segment
                            if "code segment" not in sq_text:
                                # Add reference if not present
                                updated_text = original_text + " (Refer to the code segment shown above.)"
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
                    
                    # Insert code block directly into the subquestion text
                    # Format: Code block first, then the question text
                    code_block = f"Code Segment:\n```sql\n{sql_code}\n```\n\n"
                    
                    # Prepend code block to subquestion text
                    sq["text"] = code_block + updated_text
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
        import re
        
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
                            self.log(f"    🔧 Fixed subquestion reference: ({start_ref}) to ({end_ref}) → ({start_label}) to ({end_label}) in subquestion {sq.get('label', idx)}")
                            break
        
        return parsed

    def _generate_sql_code_for_context(self, question_text: str, pattern_label: str, subquestion_text: str) -> str:
        """
        Generate appropriate SQL code based on question context.
        
        Args:
            question_text: Main question text
            pattern_label: Topic/pattern label
            subquestion_text: Subquestion text for context
            
        Returns:
            SQL code string or empty string if no code needed
        """
        # Determine SQL code type based on context
        question_lower = question_text.lower()
        sq_lower = subquestion_text.lower()
        
        # Check what type of SQL statement is being asked about
        if "jdbc" in sq_lower or "jdbc api" in sq_lower:
            # JDBC-related code
            return """PreparedStatement pstmt = connection.prepareStatement(
    "SELECT * FROM Employees WHERE Department = ?");
pstmt.setString(1, "IT");
ResultSet rs = pstmt.executeQuery();"""
        
        elif "dml" in sq_lower or "data manipulation" in sq_lower or "insert" in sq_lower or "update" in sq_lower or "delete" in sq_lower:
            # DML statement
            return """UPDATE Patients 
SET Age = 25, MedicalHistory = 'Updated record'
WHERE PatientID = 'P001';"""
        
        elif "ddl" in sq_lower or "data definition" in sq_lower or "create table" in sq_lower:
            # DDL statement
            return """CREATE TABLE Patients (
    PatientID CHAR(10) PRIMARY KEY,
    Name VARCHAR(50),
    Age INT,
    MedicalHistory VARCHAR(500)
);"""
        
        elif "select" in sq_lower or "query" in sq_lower or "retrieve" in sq_lower:
            # SELECT statement
            return """SELECT PatientID, Name, Age 
FROM Patients 
WHERE Age > 18
ORDER BY Name;"""
        
        elif "t-sql" in sq_lower or "transact-sql" in sq_lower:
            # T-SQL statement
            return """SELECT PatientID, Name, Age
FROM Patients
WHERE Age BETWEEN 18 AND 65;"""
        
        else:
            # Default: Generic SQL SELECT statement
            return """SELECT * FROM Patients 
WHERE PatientID = 'P001';"""
    
    def _build_generation_prompt(self, slot, template, context, global_context, feedback=None, *, banned_topics=None) -> str:
        """Mode 1: Pure Generation from Constraints (No past text shown)."""
        
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
        
        CRITICAL CONSTRAINTS (ZERO TOLERANCE - VIOLATIONS WILL CAUSE REJECTION):
        1. **NO PLACEHOLDERS**: Never use "...", "TBD", "[insert", "[placeholder", or any placeholder text. Every field must have complete, valid content.
        2. **MARKS MUST SUM EXACTLY**: Sub-question marks must sum to exactly {slot.get('target_marks')}. Double-check your math.
        3. **EACH SUBQUESTION MUST BE SEMANTICALLY DISTINCT**: Use different task verbs/intents (e.g., "define", "identify", "draw", "analyze", "calculate"). No duplicate or near-duplicate questions.
        4. **NO "DESCRIBED ABOVE" REFERENCES**: Never say "described above", "as shown above", "diagram above" unless you have already included the described content in the question stem.
        5. **VALID JSON ONLY**: Output must be valid JSON matching the exact schema below. No syntax errors.
        
        {"6. **ER/EER QUESTION REQUIREMENTS**: " if is_er_question else ""}{"The question stem MUST include a scenario block (2-5 sentences) describing:" if is_er_question else ""}
        {"   - Entities and their attributes" if is_er_question else ""}
        {"   - Relationships between entities" if is_er_question else ""}
        {"   - Real-world context (e.g., university, hospital, library)" if is_er_question else ""}
        {"   Then subquestions should: identify entities/attributes, identify relationships/cardinalities, draw ER/EER diagram (use [DIAGRAM PLACEHOLDER]), map to relational schema." if is_er_question else ""}
        
        {"6. **NORMALIZATION QUESTION REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if is_norm_question else ""}{"The question stem MUST include BOTH of the following:" if is_norm_question else ""}
        {"   - A relation schema in EXACT format: 'Consider a relation R(A, B, C, D) with...' OR 'Consider the following relation schema: RelationName (Attr1, Attr2, Attr3)'" if is_norm_question else ""}
        {"   - Functional dependencies in EXACT format: 'F = {A->B, B->C}' OR 'FD1: A → B, FD2: B → C' OR 'functional dependencies: A->B, B->C'" if is_norm_question else ""}
        {"   " if is_norm_question else ""}
        {"   EXAMPLE OF CORRECT FORMAT:" if is_norm_question else ""}
        {"   'Consider a relation R(ProjectNo, ProjectName, EmpNo, EmpName, DeptNo, DeptName) with the following set of functional dependencies F over R: F={{ ProjectNo->ProjectName, DeptNo->DeptName, EmpNo->EmpName }}'" if is_norm_question else ""}
        {"   " if is_norm_question else ""}
        {"   ⚠️ WITHOUT A RELATION SCHEMA AND FUNCTIONAL DEPENDENCIES IN THE STEM, THE QUESTION WILL BE REJECTED IMMEDIATELY." if is_norm_question else ""}
        {"   Then subquestions should ask for normalization steps to 3NF/BCNF and final decomposition." if is_norm_question else ""}
        
        {"6. **RELATIONAL ALGEBRA QUESTION REQUIREMENTS** (CRITICAL - MUST FOLLOW): " if is_rel_algebra_question else ""}{"The question stem MUST include:" if is_rel_algebra_question else ""}
        {"   - A scenario description (2-3 sentences) explaining the database context" if is_rel_algebra_question else ""}
        {"   - ALL relations with their attributes listed explicitly in the format: 'relation_name (attr1, attr2, attr3)'" if is_rel_algebra_question else ""}
        {"   - Each relation must be on a separate line for clarity" if is_rel_algebra_question else ""}
        {"   " if is_rel_algebra_question else ""}
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
        7. ONLY change scenario-specific details (person names, organization names, database names, entity names, relation names)
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
        
        if feedback:
            prompt += f"\n\nCRITIC FEEDBACK FROM PREVIOUS ATTEMPT (YOU MUST FIX THESE):\n{feedback}\n"
            
        return prompt

    
    def _build_paraphrase_prompt(self, slot, template, context, global_context, feedback=None, *, banned_topics=None) -> str:
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
           - ONLY change scenario-specific details (person names, organization names, database names, entity names, relation names)
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
        {"   - A relation schema in EXACT format: 'Consider a relation R(A, B, C, D) with...' OR 'Consider the following relation schema: RelationName (Attr1, Attr2, Attr3)'" if is_norm_question else ""}
        {"   - Functional dependencies in EXACT format: 'F = {{A->B, B->C}}' OR 'FD1: A → B, FD2: B → C'" if is_norm_question else ""}
        {"   ⚠️ WITHOUT A RELATION SCHEMA AND FUNCTIONAL DEPENDENCIES IN THE STEM, THE QUESTION WILL BE REJECTED IMMEDIATELY." if is_norm_question else ""}
        {"   Then subquestions should ask for normalization steps to 3NF/BCNF and final decomposition." if is_norm_question else ""}
        
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

        if feedback:
            base_prompt += f"\n\nCRITIC FEEDBACK FROM PREVIOUS ATTEMPT (YOU MUST FIX THESE ERRORS):\n{feedback}\n"
            
        return base_prompt
