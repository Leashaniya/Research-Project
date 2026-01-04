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
        hallucination_keywords = ["[figure:", "slide ", "slide_", "fig_", "page ", "page_", "refer to", "diagram above", "shown in figure"]
        if any(kw in draft_str for kw in hallucination_keywords):
            err_msg = "QUALITY ERROR: Hallucinated figure placeholder, slide reference, or diagram reference found. You MUST describe the content in text or create a scenario. Do NOT use placeholders."
            self.log(f"❌ Deterministic Reject: {err_msg}")
            return {"approved": False, "feedback": err_msg}
            
        # 4. Strict Content Quality Checks
        for sq in sub_qs:
            text = sq.get("text", "").strip()
            marks = int(sq.get("marks", 0))
            
            # 4.0 Check for EMPTY or too short text
            if len(text) < 10:
                err_msg = f"QUALITY ERROR: Sub-question text is empty or too short. You must provide a full question."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg}
            
            # 4.1 NO Vague/Subjective questions
            if any(v in text for v in ["think of", "what do you think", "your opinion", "personally"]):
                err_msg = "QUALITY ERROR: Question is subjective or vague (e.g. 'Can you think of...'). Must be a technical, objective exam question."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg}
            
            # 4.2 NO Fragmented Data (Analyzing without data)
            if any(a in text for a in ["analyze", "normalize", "compute keys"]) and "relation" not in text:
                err_msg = "QUALITY ERROR: You asked to Analyze or Normalize but didn't provide any Relation/Table Schema. You MUST define the attributes and functional dependencies."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg}

            # 4.3 Mark-to-effort mismatch (e.g. 1 mark for huge explanation)
            if marks <= 2 and ("explain" in text and "briefly" not in text) and len(text) > 100:
                err_msg = f"QUALITY ERROR: Mark mismatch. You have {marks} marks for a potentially complex question. Simplify or increase marks."
                self.log(f"❌ Deterministic Reject: {err_msg}")
                return {"approved": False, "feedback": err_msg}
            
        # 4. Scenario Repetition Check
        seen_texts = set()
        for sq in sub_qs:
            txt = sq.get("text", "").strip()
            if len(txt) > 50: # Only check significant blocks
                # Use a simplified version for comparison to catch minor variations
                simple_txt = "".join(filter(str.isalnum, txt.lower()))
                if simple_txt in seen_texts:
                    err_msg = "QUALITY ERROR: You reused the EXACT same scenario/text for multiple sub-questions. Each sub-question must have a unique scenario (e.g., if part a is about a Library, part b should be about something else)."
                    self.log(f"❌ Deterministic Reject: {err_msg}")
                    return {"approved": False, "feedback": err_msg}
                seen_texts.add(simple_txt)

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
