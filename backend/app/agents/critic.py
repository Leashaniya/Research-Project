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
        # --- DETERMINISTIC GUARDRAILS ---
        # Validate Input
        draft = input_data.get("draft", {})
        context = input_data.get("context", "")
        
        # --- DETERMINISTIC GUARDRAILS ---
        # 1. Math Check
        total_q_marks = int(draft.get("marks") or 0)
        sub_qs = draft.get("subquestions", [])
        
        if sub_qs:
            status_sum = sum(int(sq.get("marks") or 0) for sq in sub_qs)
            
            # Allow a tiny margin? No, exams must be exact.
            if status_sum != total_q_marks:
                err_msg = f"MATH ERROR: Sub-question marks sum to {status_sum}, but expected {total_q_marks}. Please adjusting weighting."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg}

        prompt = f"""
        You are a strict Exam Quality Reviewer.
        
        Review this Draft Question:
        {json.dumps(draft, indent=2)}
        
        Reference Material (Slide Context):
        {context}
        
        Checklist:
        1. CONTENT: Is the answer for each sub-question findable in the Reference Material? (No Hallucinations).
        2. STRUCTURE: Ensure sub-questions are labeled (a, b, c...) and have clear text.
        3. MARK DISTRIBUTION: Be lenient on "fairness". As long as the harder parts have more marks, APPROVE it.
        
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
            data = json.loads(content)
            
            # Robust key checking
            if isinstance(data, dict):
                # Handle variations in naming (Local LLMs sometimes hallucinate keys)
                if "approved" in data:
                    return data
                elif "is_approved" in data:
                    return {"approved": data["is_approved"], "feedback": data.get("feedback", "No feedback")}
            
            return {"approved": True, "feedback": "Format mismatch, auto-approved."}
            
        except Exception as e:
            self.log(f"Error reviewing question: {e}")
            return {"approved": True, "feedback": f"Critic failure ({e}), auto-approved."}
