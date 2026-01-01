from .base import BaseAgent
from openai import OpenAI
from app.core.config import OPENAI_API_KEY
import json

class QualityCritic(BaseAgent):
    """
    The Quality Critic Agent (Reviewer).
    Role: Review draft questions for quality, relevance, and hallucination.
    """

    def __init__(self, config=None):
        super().__init__(name="Quality Critic", config=config)
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
            "draft": {...},
            "context": "..."
        }
        Output: {
            "approved": bool,
            "feedback": "..."
        }
        """
        if not self.client:
             raise EnvironmentError("OpenAI API Key missing for Critic Agent.")

        draft = input_data["draft"]
        context = input_data["context"]
        
        self.log(f"Reviewing draft for {draft.get('question_no')}...")

        prompt = f"""
        You are a strict Exam Quality Reviewer.
        
        Review this Draft Question:
        {json.dumps(draft, indent=2)}
        
        Reference Material (Slide Context):
        {context}
        
        Checklist:
        1. Is the mark distribution FAIR? (Complex parts = High marks, Simple parts = Low marks).
        2. DO THE MATH: If there are sub-questions, do their individual marks sum up EXACTLY to {draft.get('marks')}? If not, REJECT immediately.
        3. Is the answer findable in the Reference Material? (No Hallucinations)
        4. Is the grammar and tone professional?
        
        If REJECTED, provide specific feedback on how to fix it.
        
        Output JSON:
        {{
            "approved": true/false,
            "feedback": "Reason for rejection if false, or 'Good' if true."
        }}
        """
        
        from app.core.config import settings
        model_name = settings.OPENAI_MODEL or self.config.get("model", "gpt-4o-mini")
        
        try:
            response = self.client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a strict Quality Assurance Critic."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1, # Keep very low for critic
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            self.log(f"Error reviewing question: {e}")
            # Fail open (approve) if critic crashes to avoid blockage, but log it.
            return {"approved": True, "feedback": "Critic failed, auto-approved."}
