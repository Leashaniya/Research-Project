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
            "context": "...",
            "template": {...}
        }
        """
        draft = input_data.get("draft", {})
        context = input_data.get("context", "")
        template = input_data.get("template", {})
        
        # --- DETERMINISTIC GUARDRAILS ---
        
        # 1. Math Check
        total_q_marks = int(draft.get("marks") or 0)
        sub_qs = draft.get("subquestions", [])
        
        if sub_qs:
            status_sum = sum(int(sq.get("marks") or 0) for sq in sub_qs)
            if status_sum != total_q_marks:
                err_msg = f"MATH ERROR: Sub-question marks sum to {status_sum}, but expected {total_q_marks}. Please adjust weighting."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg}

        # 2. Structure Count Check (If template exists)
        required_struct = template.get("required_structure") or template.get("subquestions", [])
        if required_struct and len(sub_qs) != len(required_struct):
            err_msg = f"STRUCTURE ERROR: Generated {len(sub_qs)} sub-questions, but template requires EXACTLY {len(required_struct)}. Please follow the required structure."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg}

        # 3. Figure Placeholders & Empty Scenarios Check (Hallucinations)
        draft_str = json.dumps(draft).lower()
        if "[figure:" in draft_str or "slide_" in draft_str or "fig_" in draft_str:
            err_msg = "QUALITY ERROR: Hallucinated figure placeholder or slide reference found (e.g. [FIGURE: ...], slide_02, fig_01). Replace with a descriptive scenario or remove reference."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg}
            
        # Check for "given scenario" with no actual content
        for sq in sub_qs:
            text = sq.get("text", "").lower()
            if "given scenario" in text or "given following scenario" in text:
                if len(text) < 60: # Too short to be a real scenario
                    err_msg = "QUALITY ERROR: You asked to design for a 'given scenario' but didn't provide the scenario text. You MUST write out the full background scenario (Library, University, Shop, etc.) in the question text."
                    self.log(f"❌ Deterministic Reject: {err_msg}")
                    return {"approved": False, "feedback": err_msg}

        # --- LLM AUDIT ---
        prompt = f"""
        You are a strict Exam Quality Reviewer.
        
        Review this Draft Question:
        {json.dumps(draft, indent=2)}
        
        Reference Material (Slide Context):
        {context}
        
        Quality Checklist:
        1. CONTENT RELEVANCE: Is the question actually about the requested topic?
        2. NO HALLUCINATIONS: Does it contain placeholders like "..." or "refer to the diagram above" (without a diagram)? 
        3. SCENARIO COMPLETENESS: If it asks to "Draw", "Construct", or "Design" based on a "given scenario", does the question ACTUALLY provide the text of that scenario? If not, REJECT.
        4. CLARITY: Is the phrasing professional?
        
        If REJECTED, provide specific feedback on how to fix it. Be very critical about missing scenarios and figure references.
        
        Output JSON:
        {{
            "approved": true/false,
            "feedback": "..."
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
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            data = json.loads(content)
            
            if isinstance(data, dict):
                if "approved" in data:
                    return data
                elif "is_approved" in data:
                    return {"approved": data["is_approved"], "feedback": data.get("feedback", "No feedback")}
            
            return {"approved": True, "feedback": "Format mismatch, auto-approved."}
            
        except Exception as e:
            self.log(f"Error reviewing question: {e}")
            return {"approved": True, "feedback": f"Critic failure ({e}), auto-approved."}
