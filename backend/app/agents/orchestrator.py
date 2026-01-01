import time
import json
from pathlib import Path
from app.agents import BlueprintAnalyst, ContentResearcher, QuestionWriter, QualityCritic
import random
from app.core.paths import OUTPUTS_DIR, ARTIFACTS_DIR

# Config
MAX_RETRIES = 2  # How many times to rewrite a question if Critic rejects it

class AgentOrchestrator:
    """
    The Board of Examiners (Orchestrator).
    Manages the workflow between:
    - Analyst (Planner)
    - Researcher (Librarian)
    - Writer (Setter)
    - Critic (Reviewer)
    """

    def __init__(self):
        self.analyst = BlueprintAnalyst()
        self.researcher = ContentResearcher()
        self.writer = QuestionWriter()
        self.critic = QualityCritic()
        
        self.out_dir = OUTPUTS_DIR / "model_papers"
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # Load Templates
        self.templates = []
        tpl_path = ARTIFACTS_DIR / "template_questions.json"
        if tpl_path.exists():
            try:
                self.templates = json.loads(tpl_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"⚠️ Error loading templates: {e}")

    def _select_template(self, q_no, marks):
        """Pick a random template that matches Q Number or Marks."""
        # Only consider templates with text
        valid = [t for t in self.templates if t.get("full_text")]
        
        if not valid:
             return {
                 "pattern_label": "General Theory",
                 "full_text": "(Reference style only) Explain the concept of X.",
                 "marks": marks
            }

        # Try match by Question Number (String vs Int usually problematic, handle both)
        # q_no might be "Q1", template q_id might be "1"
        q_num_str = str(q_no).replace("Q", "")
        
        matches = [t for t in valid if str(t.get("question_id")) == q_num_str]
        
        if not matches:
            # Fallback: Match by marks (approx (+-5))
            matches = [t for t in valid if abs(int(t.get("marks", 0)) - int(marks or 0)) <= 5]
            
        if not matches:
            matches = valid # Fallback to any valid template
            
        selected = random.choice(matches)
        return selected

    async def run_pipeline(self):
        print("\n--- AGENTIC PIPELINE STARTED ---\n")
        
        # 1. ANALYST: Get the blueprint
        blueprint = await self.analyst.run()
        exam_title = blueprint.get("exam_title", "Model Paper")
        slots = blueprint.get("question_slots", [])
        
        final_questions = []
        total_marks = 0
        
        # 2. LOOP through slots
        for slot in slots:
            q_no = slot.get("question_no") or slot.get("slot_id")
            target_marks = slot.get("target_marks")
            print(f"\n>>> Processing {q_no} ({target_marks} marks)...")
            
            # 2a. RESEARCHER: Get context
            # Select a template
            template = self._select_template(q_no, target_marks)
            
            # Use template label/text to guide the research query
            # E.g. if template is "SQL_DDL_DML", we might want to research "SQL DDL scenarios"
            # For now, we combine Exam Title + Topic + Template Label
            topic = slot.get('topics', ['General'])[0]
            query = f"{exam_title} {topic} {template.get('pattern_label', '')}"
            
            context = await self.researcher.run({"query": query})

            # 2b. WRITE - REVIEW LOOP
            approved = False
            feedback = None
            draft = None
            
            for attempt in range(MAX_RETRIES + 1):
                # Writer
                draft = await self.writer.run({
                    "slot": slot,
                    "template": template,
                    "context": context,
                    "feedback": feedback
                })
                
                # Critic
                review = await self.critic.run({
                    "draft": draft,
                    "context": context
                })
                
                if review["approved"]:
                    print(f"✅ {q_no} Approved!")
                    approved = True
                    break
                else:
                    print(f"❌ {q_no} Rejected. Feedback: {review['feedback']}")
                    feedback = review["feedback"]
            
            if not approved:
                print(f"⚠️ {q_no} forced approval after max retries.")
            
            final_questions.append(draft)
            total_marks += int(draft.get("marks", 0))

        # 3. SAVE
        paper = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": "AGENTIC_V1",
            "total_marks": total_marks,
            "questions": final_questions
        }
        
        out_path = self.out_dir / "agentic_model_paper.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(paper, f, indent=2)
            
        print(f"\n✅ Paper generated: {out_path}")
        return paper

# Entry point for pipeline_service
async def main():
    orchestrator = AgentOrchestrator()
    return await orchestrator.run_pipeline()
