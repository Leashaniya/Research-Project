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

    def _build_generation_prompt(self, slot, template, context, global_context, feedback=None, *, banned_topics=None) -> str:
        """Mode 1: Pure Generation from Constraints (No past text shown)."""
        
        topic = slot.get('topics', ['General'])[0]
        structure_fingerprint = template.get("required_structure") or [{"label": "a", "marks": slot.get("target_marks")}]
        pattern_label = template.get('pattern_label', topic).lower()
        
        # Calculate sub-question breakdown string with text patterns if available
        structure_parts = []
        for s in structure_fingerprint:
            label = s.get('label', '?')
            marks = s.get('marks', 0)
            text_pattern = s.get('text', '')  # Get stored text pattern
            if text_pattern:
                # Include the instruction pattern for preservation
                structure_parts.append(f"- Part {label}: {marks} marks\n  Instruction Pattern: \"{text_pattern}\"")
            else:
                structure_parts.append(f"- Part {label}: {marks} marks")
        structure_str = "\n".join(structure_parts)
        
        # CRITICAL: Get exact count required
        required_count = len(structure_fingerprint)
        
        # Determine if ER/EER or Normalization question
        is_er_question = "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label or "schema" in pattern_label
        is_norm_question = "normalization" in pattern_label or "normal form" in pattern_label
        
        
        er_context = ""
        used_scenarios_list = global_context.get('used_scenarios', [])
        if is_er_question:
             er_context = f"Include a UNIQUE scenario (zoo, restaurant, gym, hotel, museum, cinema, stadium, theater) DIFFERENT from: {used_scenarios_list}. Describe entities, relationships, and attributes."
        elif is_norm_question:
             er_context = f"Include a relation schema and functional dependencies from a UNIQUE scenario (airline, restaurant, gym, hotel, pharmacy, supermarket, warehouse, factory) DIFFERENT from: {used_scenarios_list}."
        else:
             er_context = f"Include relevant context and background information. Use a UNIQUE scenario DIFFERENT from: {used_scenarios_list}."

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
        - USED SCENARIOS (MUST AVOID): {global_context.get('used_scenarios', [])} 
          ⚠️ CRITICAL: You MUST use a COMPLETELY DIFFERENT, UNIQUE scenario that has NEVER been used before.
          - If used scenarios include: "library", "university", "hospital", "bank"
          - You MUST choose a DIFFERENT scenario like: "airline", "restaurant", "gym", "hotel", "school", "museum", "zoo", "pharmacy", "cinema", "supermarket", "warehouse", "factory", "park", "stadium", "theater"
          - Each question in the paper MUST have a UNIQUE scenario (no two questions can use the same scenario)
          - The scenario must be relevant to Database Management Systems and allow for the same question structure
        
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
        {"   - Real-world context: Use a UNIQUE scenario DIFFERENT from previous questions. Examples: zoo, restaurant, gym, hotel, museum, cinema, stadium, theater, park, warehouse, factory" if is_er_question else ""}
        {"   - AVOID common scenarios already used: {global_context.get('used_scenarios', [])}" if is_er_question else ""}
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
        
        ADDITIONAL CONSTRAINTS:
        - **PRESERVE INSTRUCTION PATTERNS**: If the structure includes "Instruction Pattern" text, you MUST preserve that exact instruction pattern:
          * Keep the same task verbs (e.g., "Draw", "Convert", "Extend", "Identify", "Use the attribute closure")
          * Keep the same diagram types (e.g., "ER diagram", "EER diagram", "relational model", "functional dependency diagram")
          * Keep the same instruction structure (e.g., "Convert the following EER model into the relational model", "Draw the functional dependency diagram")
          * ONLY change the scenario/context (e.g., different entities, different domain, different relation names)
          * Example: If pattern says "Convert the following EER model into the relational model", your generated question MUST say "Convert the following EER model into the relational model" (but for a different scenario)
        - **Historical Pattern Alignment**: Follow the exact structure, style, and difficulty level of past exam questions
        - **Syllabus Compliance**: Ensure all content aligns with Database Management Systems curriculum modules
        - **Past Paper Reflection**: Questions must reflect topics and patterns from historical exam papers
        - **Bloom's Taxonomy**: Ensure a mix of Recall (Define/List) and Application (Design/Analyze) as seen in past papers
        - **Single Scenario**: Use ONE cohesive scenario for all parts.
        - **SCENARIO UNIQUENESS**: The scenario you choose MUST be completely different from any scenario used in previous questions in this paper. Check USED SCENARIOS: {global_context.get('used_scenarios', [])}
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
        for s in structure_fingerprint:
            label = s.get('label', '?')
            marks = s.get('marks', 0)
            text_pattern = s.get('text', '')  # Get stored text pattern
            if text_pattern:
                # Include the instruction pattern for preservation
                structure_parts.append(f"- Part {label}: {marks} marks\n  Instruction Pattern: \"{text_pattern}\"")
            else:
                structure_parts.append(f"- Part {label}: {marks} marks")
        structure_str = "\n".join(structure_parts)
        required_count = len(structure_fingerprint)

        er_context = ""
        used_scenarios_list = global_context.get('used_scenarios', [])
        if is_er_question:
             er_context = f"Include a UNIQUE scenario (zoo, restaurant, gym, hotel, museum, cinema, stadium, theater) DIFFERENT from: {used_scenarios_list}. Describe entities, relationships, and attributes."
        elif is_norm_question:
             er_context = f"Include a relation schema and functional dependencies from a UNIQUE scenario (airline, restaurant, gym, hotel, pharmacy, supermarket, warehouse, factory) DIFFERENT from: {used_scenarios_list}."
        else:
             er_context = f"Include relevant context and background information. Use a UNIQUE scenario DIFFERENT from: {used_scenarios_list}."
        
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
        2. **PRESERVE INSTRUCTION PATTERNS**: For each sub-question, preserve the EXACT instruction pattern from the template:
           - If template says "Draw the ER diagram", your generated question MUST say "Draw the ER diagram" (but for the new scenario)
           - If template says "Extend and draw the EER diagram", your generated question MUST say "Extend and draw the EER diagram" (but for the new scenario)
           - If template says "Convert the following EER model into the relational model", your generated question MUST say "Convert the following EER model into the relational model" (but for the new scenario)
           - Preserve the exact task verbs, diagram types, and instruction structure
           - ONLY change the scenario/context (e.g., "university" → "hospital", "library" → "bank")
        3. **Historical Pattern Alignment**: Maintain the exact structure, style, and difficulty level of the reference question
        4. **Syllabus Compliance**: Ensure all content aligns with Database Management Systems curriculum modules
        5. **SCENARIO DIVERSITY (CRITICAL)**: You MUST use a COMPLETELY DIFFERENT, UNIQUE scenario that has NEVER been used before:
           - If past papers use: "library", "university", "hospital", "bank", "bookstore"
           - You MUST use a DIFFERENT scenario like: "airline", "restaurant", "gym", "hotel", "school", "museum", "zoo", "pharmacy", "cinema", "supermarket", "warehouse", "factory", "park", "stadium", "theater"
           - Each question in the paper MUST have a UNIQUE scenario (no two questions can use the same scenario)
           - The scenario must be relevant to Database Management Systems and allow for the same question structure
           - USED SCENARIOS TO AVOID: {global_context.get('used_scenarios', [])}
           - Example: If Q1 uses "hospital", Q2 cannot use "hospital" - use "airline" or "restaurant" instead
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
        
        {"9. **ER/EER QUESTION REQUIREMENTS**: " if is_er_question else ""}{"The question stem MUST include a scenario block (2-5 sentences) describing entities, relationships, and attributes. Use a UNIQUE scenario (zoo, restaurant, gym, hotel, museum, cinema, stadium, theater) DIFFERENT from previous questions. AVOID: {global_context.get('used_scenarios', [])}. Then subquestions should: identify entities/attributes, identify relationships/cardinalities, draw ER/EER diagram (use [DIAGRAM PLACEHOLDER]), map to relational schema." if is_er_question else ""}
        
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
