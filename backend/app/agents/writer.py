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

        prompt = self._build_prompt(slot, template, context, feedback)
        
        q_label = slot.get('question_no') or slot.get('slot_id') or "Q?"
        self.log(f"Drafting question for {q_label} ({slot.get('target_marks')} marks)...")
        
        from app.core.config import settings
        model_name = settings.OPENAI_MODEL or self.config.get("model", "gpt-4o-mini")
        
        try:
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are an expert University Exam Question Setter."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4, # Lower for local models
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            self.log(f"Error drafting question: {e}")
            raise e

    def _build_prompt(self, slot, template, context, feedback=None) -> str:
        base_prompt = f"""
        Generate ONE university exam question.
        
        Specifications:
        - Question Number: {slot.get('question_no') or slot.get('slot_id') or "Q?"}
        - Marks: {slot.get('target_marks')}
        - Type: {template.get('pattern_label', 'General')}
        - Topic Context: {context}
        
        CRITICAL AUTHENTICITY RULE:
        SLIIT papers usually follow a "50/50" split for sub-questions:
        1. RECALL: (e.g. List 3 properties, Define X, Identify entities). 
        2. APPLY/DESIGN: (e.g. Construct EER, Calculate blocks, Map to relational).
        Ensure this specific question includes at least one sub-question that asks for a definition or listing to match historical standards.
        
        CRITICAL STRUCTURE RULE:
        """
        
        # Check if we have a canonical structure to enforce
        required_structure = template.get("required_structure", [])
        if required_structure:
            base_prompt += f"""
        **EXACT STRUCTURE REQUIRED** (Based on historical pattern from {template.get('full_text', 'past papers')}):
        - You MUST create EXACTLY {len(required_structure)} sub-questions
        - Follow this EXACT mark distribution:
"""
            for struct in required_structure:
                base_prompt += f"          * Part {struct['label']}: {struct['marks']} marks ({struct['type']} type)\n"
            
            base_prompt += f"""
        - The marks MUST sum to exactly {slot.get('target_marks')}
        - Do NOT deviate from this structure
        """
        else:
            base_prompt += f"""
        - For 20-mark questions, create AT LEAST 3 sub-questions (a, b, c, and optionally d).
        - For 10-15 mark questions, create 2-3 sub-questions.
        - Sub-question marks MUST sum up exactly to {slot.get('target_marks')}.
        - Explicitly state the marks for each sub-question in parentheses, e.g. (5 marks).
        - **DISTRIBUTION STRATEGY**: Assign marks proportional to difficulty. 
          * Lower marks (2-5) for Definitions/Recall.
          * Higher marks (6-12) for Analysis/Design/Calculation.
        """
        
        base_prompt += f"""
        
        Style Reference (Template - DO NOT COPY):
        {template.get('full_text')}
        
        Output JSON:
        {{
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "subquestions": [
                {{
                    "label": "a",
                    "text": "...",
                    "marks": 4
                }},
                {{
                    "label": "b",
                    "text": "...",
                    "marks": 6
                }},
                {{
                    "label": "c",
                    "text": "...",
                    "marks": 10
                }}
            ]
        }}
            ]
        }}
        """
        
        if feedback:
            base_prompt += f"\n\nCRITIC FEEDBACK (FIX THIS): {feedback}\n"
            base_prompt += "Ensure the new draft resolves the issue raised by the critic."
            
        return base_prompt
