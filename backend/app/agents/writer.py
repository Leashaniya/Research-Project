from .base import BaseAgent
from openai import OpenAI
from app.core.config import OPENAI_API_KEY
import json

class QuestionWriter(BaseAgent):
    """
    The Question Writer Agent (Setter).
    Role: Draft questions based on bluepint specs + slide context.
    """

    def __init__(self, config=None):
        super().__init__(name="Question Writer", config=config)
        self.api_key = OPENAI_API_KEY
        self.client = None
        
        # Local LLM Support
        from app.core.config import settings
        base_url = settings.OPENAI_BASE_URL
        
        if self.api_key:
            if base_url:
                self.client = OpenAI(api_key=self.api_key, base_url=base_url)
                self.log(f"Using Local LLM at: {base_url}")
            else:
                self.client = OpenAI(api_key=self.api_key)

    async def run(self, input_data: dict) -> dict:
        """
        Input: {
            "slot": {...},
            "template": {...},
            "context": "...",
            "feedback": "..." (optional, from Critic)
        }
        Output: JSON dict with question details.
        """
        if not self.client:
             raise EnvironmentError("AI Cloud API Key missing for Writer Agent.")

        slot = input_data["slot"]
        template = input_data["template"]
        context = input_data["context"]
        feedback = input_data.get("feedback")

        global_context = input_data.get("global_context", {})
        prompt = self._build_prompt(slot, template, context, global_context, feedback)
        
        q_label = slot.get('question_no') or slot.get('slot_id') or "Q?"
        self.log(f"Drafting question for {q_label} ({slot.get('target_marks')} marks)...")
        
        from app.core.config import settings
        model_name = settings.OPENAI_MODEL or self.config.get("model", "gpt-4o-mini")
        
        try:
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": """You are an expert University Exam Question Setter for Database Systems.
    ULTRA-STRICT RULES (ZERO TOLERANCE):
    1. DATABASE SYSTEMS ONLY (CRITICAL): This is a Database Systems exam. EVERY question MUST be about database concepts ONLY:
       - ER/EER diagrams, Normalization, SQL queries, Transactions, Indexing, Relational Model
       - Functional Dependencies, Keys (Primary, Foreign, Candidate), Constraints
       - Database Design, Schema Design, Data Integrity, Concurrency Control
       - DO NOT include: Networking (frame bytes, TCP/IP), Operating Systems, Software Engineering, Web Development, Machine Learning, or ANY non-database topic.
    2. NO SLIDE/FIGURE REFERENCES: Never use "Slide X", "Figure Y", "[FIGURE]", or "Refer to...". If context mentions a slide, you MUST extract the actual technical content (e.g., a table, a diagram's logic) and describe it in full sentences.
    3. SCENARIO MANDATORY: If you ask to 'Draw', 'Design', or 'Analyze', you MUST write a detailed, unique scenario yourself inside the question text.
    4. UNIQUE SCENARIOS: DO NOT reuse any scenario context (e.g., student/course) from previous questions.
    5. NO VAGUE QUESTIONS: DO NOT ask "Can you think of...", "What do you think...", or "Give your opinion". Questions must be objective and technical.
    6. NO BLANK QUESTIONS: Every sub-question MUST have a substantial 'text' field. Do NOT leave text empty or just put a label.
    7. COGNITIVE LEVEL (BLOOM'S): Target 30% Understand, 40% Apply/Analyze, 30% Create/Design. Avoid too many 'Explain' questions.
"""},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4, # Lower for local models
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            parsed = json.loads(content)
            
            # Validation: Check for empty text
            for sq in parsed.get("subquestions", []):
                if not sq.get("text") or len(sq.get("text").strip()) < 5:
                    raise ValueError(f"Generated empty question text for label {sq.get('label')}")
                    
            return parsed
        except Exception as e:
            self.log(f"Error drafting question: {e}")
            raise e

    def _build_prompt(self, slot, template, context, global_context, feedback=None) -> str:
        base_prompt = f"""
        Generate ONE high-quality university exam question for a Database Systems course.
        
        CRITICAL: This is a Database Systems exam. ALL questions MUST be about database concepts:
        - ER/EER diagrams, Normalization, SQL, Transactions, Indexing, Relational Model
        - Functional Dependencies, Keys, Constraints, Database Design, Schema Design
        - DO NOT include networking, operating systems, software engineering, web development, or any non-database topics.
        
        Specifications:
        - Question Number: {slot.get('question_no') or slot.get('slot_id') or "Q?"}
        - Total Marks: {slot.get('target_marks')}
        - Topic Context: {context}
        
        GLOBAL UNIQUENESS (DO NOT REUSE THESE):
        - Topics already used: {global_context.get('used_topics', [])}
        - PREVIOUS SCENARIOS (DO NOT REUSE): {global_context.get('used_scenarios', [])}
        - FORBIDDEN TOPICS (STRICTLY PROHIBITED): {global_context.get('forbidden_topics', [])}
        - IMPORTANT: If the requested template asks for a FORBIDDEN TOPIC, you MUST change the topic to something else from the syllabus (e.g. Normalization -> SQL, ER -> Relational Map). VALIDITY > TEMPLATE.
        
        CRITICAL CONTENT RULES (ZERO TOLERANCE):
        1. **SINGLE SCENARIO ENFORCEMENT**: If this question involves a scenario (e.g. University, Hospital, Bank), it must be the ONLY scenario used for the ENTIRE question (all sub-questions). DO NOT mix multiple scenarios.
        2. **NO MCQs**: This is a structural paper. DO NOT generate Multiple Choice Questions (A, B, C, D). All questions must be descriptive or design-based.
        3. **FIGURE PLACEHOLDERS**: If a diagram is required, DO NOT describe it. Instead, insert exactly: `[PLACEHOLDER FIGURE] (Description of what diagram should show)`.
        4. **NO FIGURE REFERENCES**: Do NOT refer to "Figure 1", "Slide 2", etc.
        5. **NO EMPTY QUESTIONS**: Every sub-question `text` field must have substantial content.
        
        CRITICAL AUTHENTICITY RULE:
        SLIIT papers usually follow a "50/50" split for sub-questions:
        1. RECALL: (e.g. List 3 properties, Define X, Identify entities). 
        2. APPLY/DESIGN: (e.g. Construct EER, Calculate blocks, Map to relational).
        Ensure this specific question includes balance between definitions and practical application.
        
        CRITICAL STRUCTURE RULE:
        """
        
        # Check if we have a canonical structure to enforce
        required_structure = template.get("required_structure", [])
        if required_structure:
            base_prompt += f"""
        **EXACT STRUCTURE REQUIRED** (Follow this sub-question count and mark distribution):
        - You MUST create EXACTLY {len(required_structure)} sub-questions. No more, no less.
        - Follow this EXACT mark distribution:
"""
            # Calculate Scaling
            target_marks = int(slot.get('target_marks') or 0)
            template_total = sum(int(i.get("marks") or 0) for i in required_structure)
            
            scaled_structure = []
            current_sum = 0
            
            for idx, struct in enumerate(required_structure):
                raw_marks = int(struct.get("marks") or 0)
                new_marks = raw_marks
                
                if template_total > 0 and template_total != target_marks:
                    ratio = target_marks / template_total
                    new_marks = int(round(raw_marks * ratio))
                    if raw_marks > 0 and new_marks == 0:
                        new_marks = 1
                
                scaled_structure.append({"label": struct.get("label"), "type": struct.get("type"), "marks": new_marks})
                current_sum += new_marks
                
            # Distribute Remainder
            diff = target_marks - current_sum
            if diff != 0 and scaled_structure:
                 max_idx = max(range(len(scaled_structure)), key=lambda i: scaled_structure[i]['marks'])
                 scaled_structure[max_idx]['marks'] += diff

            for struct in scaled_structure:
                base_prompt += f"          * Part {struct['label']}: {struct['marks']} marks\n"
            
            base_prompt += f"""
        - The sub-question marks MUST sum to exactly {slot.get('target_marks')}
        - Do NOT deviate from this structure.
        """
        else:
            base_prompt += f"""
        - Create 3-7 sub-questions (a, b, c, d, e, f, g). DO NOT EXCEED 7 SUB-QUESTIONS.
        - Consolidate small questions if you have more than 7.
        - Sub-question marks MUST sum up exactly to {slot.get('target_marks')}.
        - Explicitly state the marks for each sub-question in parentheses, e.g. (5 marks).
        """
        
        base_prompt += f"""
        
        Output valid JSON:
        {{
            "reasoning": "STEP-BY-STEP PLAN: 1. Scenario: [Describe your unique scenario here] 2. Sub-questions: [Plan parts a-e] 3. Marks Check: [Ensure sum is {slot.get('target_marks')}]",
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "subquestions": [
                {{
                    "label": "a",
                    "text": "...",
                    "marks": 5
                }}
            ]
        }}
        """
        
        if feedback:
            base_prompt += f"\n\nCRITIC FEEDBACK FROM PREVIOUS ATTEMPT (FIX THESE ERRORS): {{feedback}}\n"
            
        return base_prompt
