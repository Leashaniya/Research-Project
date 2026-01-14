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
        needs_diagram = input_data.get("needs_diagram", False)
        diagram_type = input_data.get("diagram_type", None)
        
        # Select Prompt Strategy
        if mode == "generate":
            prompt = self._build_generation_prompt(slot, template, context, global_context, feedback, needs_diagram, diagram_type)
            self.log(f"Drafting question for {slot.get('question_no')} (Mode: GEN-FROM-SCRATCH)...")
        else:
            prompt = self._build_paraphrase_prompt(slot, template, context, global_context, feedback, needs_diagram, diagram_type)
            self.log(f"Drafting question for {slot.get('question_no')} (Mode: TEMPLATE-PARAPHRASE)...")
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
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

    def _build_generation_prompt(self, slot, template, context, global_context, feedback=None, needs_diagram=False, diagram_type=None) -> str:
        """Mode 1: Pure Generation from Constraints (No past text shown)."""
        
        topic = slot.get('topics', ['General'])[0]
        structure_fingerprint = template.get("required_structure") or [{"label": "a", "marks": slot.get("target_marks")}]
        pattern_label = template.get('pattern_label', topic).lower()
        
        # Calculate sub-question breakdown string
        structure_str = "\n".join([f"- Part {s.get('label', '?')}: {s.get('marks')} marks" for s in structure_fingerprint])
        
        # Determine if ER/EER or Normalization question
        is_er_question = "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label
        is_norm_question = "normalization" in pattern_label or "normal form" in pattern_label
        
        prompt = f"""
        You are an expert Exam Setter for a Database Management Systems course.
        Create a NEW, ORIGINAL exam question based on the following constraints.
        
        METADATA:
        - Question No: {slot.get('question_no', '?')}
        - Total Marks: {slot.get('target_marks')}
        - Primary Topic: {template.get('pattern_label', topic)}
        - Module Context: {context[:500]}...
        
        REQUIRED STRUCTURE:
{structure_str}
        
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
        
        {"6. **NORMALIZATION QUESTION REQUIREMENTS**: " if is_norm_question else ""}{"The question stem MUST include:" if is_norm_question else ""}
        {"   - A relation schema (e.g., R(A,B,C) or explicit attributes)" if is_norm_question else ""}
        {"   - Functional dependencies (FDs) in standard notation" if is_norm_question else ""}
        {"   Then subquestions should ask for normalization steps to 3NF/BCNF and final decomposition." if is_norm_question else ""}
        
        {"7. **DIAGRAM PLACEHOLDER**: " if needs_diagram else ""}{f"If a {diagram_type} diagram is required, include in the appropriate subquestion:" if needs_diagram else ""}
        {"   '[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]'" if needs_diagram else ""}
        {"   Do NOT use Mermaid code or image references." if needs_diagram else ""}
        
        ADDITIONAL CONSTRAINTS:
        - **Bloom's Taxonomy**: Ensure a mix of Recall (Define/List) and Application (Design/Analyze).
        - **Single Scenario**: Use ONE cohesive scenario for all parts.
        - **Authenticity**: Write a real, solvable problem with specific details.
        - **Database Systems Only**: All content must be relevant to Database Management Systems.
        
        OUTPUT JSON FORMAT (STRICT SCHEMA):
        {{
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "text": "Question stem text here (minimum 50 characters). This is the main scenario/context for all subquestions. {"Include a scenario describing entities, relationships, and attributes." if is_er_question else "Include a relation schema and functional dependencies." if is_norm_question else "Include relevant context and background information."}",
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

    def _build_paraphrase_prompt(self, slot, template, context, global_context, feedback=None, needs_diagram=False, diagram_type=None) -> str:
        """Mode 2: Paraphrasing (Keep structure, change content)."""
        pattern_label = template.get('pattern_label', '').lower()
        is_er_question = "er" in pattern_label or "eer" in pattern_label or "diagram" in pattern_label
        is_norm_question = "normalization" in pattern_label or "normal form" in pattern_label
        
        base_prompt = f"""
        Generate ONE high-quality university exam question for a Database Systems course.
        
        TASK:
        You are given a 'Reference Question' from a past paper.
        Your goal is to WRITE A NEW QUESTION that has the EXACT SAME STRUCTURE and DIFFICULTY, but applies to a COMPLETELY DIFFERENT SCENARIO.
        
        REFERENCE QUESTION:
        {template.get('full_text', '')}
        
        CONSTRAINTS:
        1. **Keep Structure**: If original has 3 parts (a,b,c) with 5,5,10 marks, you MUST keep that EXACTLY.
        2. **Change Scenario**: If original is about a Bank, you write about a Library or Hospital (completely different).
        3. **Keep Topic**: If original asks to Draw ERD, you ask to Draw ERD (but for the new scenario).
        4. **NO PLAGIARISM**: Do not copy the text. Re-invent it completely.
        
        Specifications:
        - Question Number: {slot.get('question_no') or slot.get('slot_id') or "Q?"}
        - Total Marks: {slot.get('target_marks')}
        - Topic Context: {context[:500]}...
        
        GLOBAL UNIQUENESS (DO NOT REUSE THESE):
        - Topics already used: {global_context.get('used_topics', [])}
        - PREVIOUS SCENARIOS (DO NOT REUSE): {global_context.get('used_scenarios', [])}
        
        CRITICAL CONTENT RULES (ZERO TOLERANCE - VIOLATIONS WILL CAUSE REJECTION):
        1. **NO PLACEHOLDERS**: Never use "...", "TBD", "[insert", "[placeholder", or any placeholder text. Every field must have complete, valid content.
        2. **MARKS MUST SUM EXACTLY**: Sub-question marks must sum to exactly {slot.get('target_marks')}. Double-check your math.
        3. **EACH SUBQUESTION MUST BE SEMANTICALLY DISTINCT**: Use different task verbs/intents. No duplicate or near-duplicate questions.
        4. **NO "DESCRIBED ABOVE" REFERENCES**: Never say "described above", "as shown above" unless you have already included the described content.
        5. **SINGLE SCENARIO ENFORCEMENT**: If this question involves a scenario, it must be the ONLY scenario used for the ENTIRE question (all sub-questions). DO NOT mix multiple scenarios.
        6. **NO MCQs**: This is a structural paper. DO NOT generate Multiple Choice Questions. All questions must be descriptive or design-based.
        7. **NO FIGURE REFERENCES**: Do NOT refer to "Figure 1", "Slide 2", etc.
        8. **NO EMPTY QUESTIONS**: Every sub-question `text` field must have substantial content (minimum 20 characters).
        
        {"9. **ER/EER QUESTION REQUIREMENTS**: " if is_er_question else ""}{"The question stem MUST include a scenario block (2-5 sentences) describing entities, relationships, and attributes. Then subquestions should: identify entities/attributes, identify relationships/cardinalities, draw ER/EER diagram (use [DIAGRAM PLACEHOLDER]), map to relational schema." if is_er_question else ""}
        
        {"9. **NORMALIZATION QUESTION REQUIREMENTS**: " if is_norm_question else ""}{"The question stem MUST include a relation schema (e.g., R(A,B,C)) and functional dependencies. Then subquestions should ask for normalization steps to 3NF/BCNF and final decomposition." if is_norm_question else ""}
        
        {"10. **DIAGRAM PLACEHOLDER**: " if needs_diagram else ""}{f"If a {diagram_type} diagram is required, include: '[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram for the scenario in the answer booklet.]' Do NOT use Mermaid code." if needs_diagram else ""}
        
        Output valid JSON (STRICT SCHEMA):
        {{
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "text": "Question stem text here (minimum 50 characters). This is the main scenario/context for all subquestions. {"Include a scenario describing entities, relationships, and attributes." if is_er_question else "Include a relation schema and functional dependencies." if is_norm_question else "Include relevant context and background information."}",
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
        - If ER/EER question: include scenario in stem.
        - If Normalization question: include schema and FDs in stem.
        """

        if feedback:
            base_prompt += f"\n\nCRITIC FEEDBACK FROM PREVIOUS ATTEMPT (YOU MUST FIX THESE ERRORS):\n{feedback}\n"
            
        return base_prompt
