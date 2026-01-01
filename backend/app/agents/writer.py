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
             raise EnvironmentError("OpenAI API Key missing for Writer Agent.")

        slot = input_data["slot"]
        template = input_data["template"]
        context = input_data["context"]
        feedback = input_data.get("feedback")

        prompt = self._build_prompt(slot, template, context, feedback)
        
        self.log(f"Drafting question for {slot.get('question_no')} ({slot.get('target_marks')} marks)...")
        
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
        - Question Number: {slot.get('question_no')}
        - Marks: {slot.get('target_marks')}
        - Type: {template.get('pattern_label', 'General')}
        - Topic Context: {context}
        
        CRITICAL RULE:
        - If you create sub-questions (e.g. a, b, c), their marks MUST sum up exactly to {slot.get('target_marks')}.
        - Explicitly state the marks for each sub-question in parentheses, e.g. (5 marks).
        - **DISTRIBUTION STRATEGY**: Assign marks proportional to difficulty. 
          * Lower marks (2-4) for Definitions/Recall.
          * Higher marks (5-10+) for Analysis/Design/Calculation.
        
        Style Reference (Template - DO NOT COPY):
        {template.get('full_text')}
        
        Output JSON:
        {{
            "question_no": "{slot.get('question_no')}",
            "marks": {slot.get('target_marks')},
            "text": "..."
        }}
        """
        
        if feedback:
            base_prompt += f"\n\nCRITIC FEEDBACK (FIX THIS): {feedback}\n"
            base_prompt += "Ensure the new draft resolves the issue raised by the critic."
            
        return base_prompt
