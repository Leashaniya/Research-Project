import time
import json
from pathlib import Path
from app.agents import BlueprintAnalyst, ContentResearcher, QuestionWriter, QualityCritic
from app.services.pdf_service import PDFService
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
        self.checkpoint_path = self.out_dir / "generation_checkpoint.json"

        # Load Templates
        tpl_path = ARTIFACTS_DIR / "template_questions.json"
        if tpl_path.exists():
            try:
                self.templates = json.loads(tpl_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"⚠️ Error loading templates: {e}")
        
        # Load Canonical Templates (Frequency-based)
        canonical_path = ARTIFACTS_DIR / "canonical_templates.json"
        self.canonical_templates = {}
        if canonical_path.exists():
            try:
                self.canonical_templates = json.loads(canonical_path.read_text(encoding="utf-8"))
                print(f"✅ Loaded canonical templates for {len(self.canonical_templates)} question positions")
            except Exception as e:
                print(f"⚠️ Error loading canonical templates: {e}")

    def _get_canonical_template(self, q_no):
        """Get the canonical template for a question position."""
        canonical = self.canonical_templates.get(q_no)
        if canonical:
            return canonical
        
        # Fallback to old random selection if no canonical template
        print(f"⚠️ No canonical template for {q_no}, using fallback")
        return self._select_template(q_no, None)
    
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

    def _render_question(self, draft):
        """Convert structured subquestions into a beautiful string."""
        main_q_no = draft.get("question_no", "?")
        sub_qs = draft.get("subquestions", [])
        
        if not sub_qs:
            return draft.get("text", "...")
            
        lines = []
        for sq in sub_qs:
            label = sq.get("label", "?")
            text = sq.get("text", "...")
            marks = sq.get("marks", 0)
            lines.append(f"{label}) {text} ({marks} marks)")
            
        return "\n".join(lines)

    async def run_pipeline(self):
        print("\n--- AGENTIC PIPELINE STARTED ---\n")
        
        # 1. ANALYST: Get the blueprint
        blueprint = await self.analyst.run()
        exam_title = blueprint.get("exam_title", "Model Paper")
        slots = blueprint.get("question_slots", [])
        
        # 1.5 CHECKPOINT: Load existing progress if any
        checkpoint_data = {}
        if self.checkpoint_path.exists():
            try:
                checkpoint_data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
                print(f"🔄 Resuming from checkpoint: {len(checkpoint_data.get('questions', []))} questions already finished.")
            except Exception:
                pass
        
        final_questions = checkpoint_data.get("questions", [])
        total_marks = sum(int(q.get("marks", 0)) for q in final_questions)
        
        # 2. LOOP through slots
        for slot in slots:
            q_no = slot.get("question_no") or slot.get("slot_id") or f"Q{slot.get('position', '?')}"
            target_marks = slot.get("target_marks")

            # Check if already in checkpoint
            # Robust check: handle "Q1" vs "1" or "None"
            checkpoint_match = False
            for q in final_questions:
                saved_no = str(q.get("question_no", "")).replace("Q", "")
                current_no = str(q_no).replace("Q", "")
                if saved_no == current_no:
                    checkpoint_match = True
                    break
            
            if checkpoint_match:
                print(f"⏩ Skipping {q_no} (Already in checkpoint)")
                continue

            print(f"\n>>> Processing {q_no} ({target_marks} marks)...")
            
            # 2a. Get Canonical Template (Frequency-based)
            canonical = self._get_canonical_template(q_no)
            
            # Build template dict for backward compatibility
            if isinstance(canonical, dict) and "subquestion_structure" in canonical:
                # It's a canonical template
                template = {
                    "pattern_label": canonical.get("dominant_topic", "General"),
                    "full_text": f"Reference: {canonical.get('source_paper', 'Unknown')}",
                    "marks": canonical.get("total_marks", target_marks),
                    "required_structure": canonical.get("subquestion_structure", [])
                }
            else:
                # Fallback to old template
                template = canonical if canonical else self._select_template(q_no, target_marks)
            
            # 2b. RESEARCHER: Get context
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
                    "context": context,
                    "q_no": q_no  # Pass q_no to fix "None" label
                })
                
                is_approved = review.get("approved", True) # Fallback to True if key missing
                
                if is_approved:
                    print(f"✅ {q_no} Approved!")
                    approved = True
                    break
                else:
                    print(f"❌ {q_no} Rejected. Feedback: {review['feedback']}")
                    feedback = review["feedback"]
            
            if not approved:
                print(f"⚠️ {q_no} forced approval after max retries.")
            
            # 2c. RENDER the question for final display
            draft["question_no"] = q_no
            draft["text"] = self._render_question(draft)
            
            final_questions.append(draft)
            total_marks += int(draft.get("marks", 0))

            # SAVE CHECKPOINT
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({"questions": final_questions}, f, indent=2)

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
            
        print(f"\n✅ JSON Paper generated: {out_path}")

        # 4. PDF EXPORT
        pdf_path = str(out_path).replace(".json", ".pdf")
        try:
            PDFService.generate_pdf(paper, pdf_path)
            print(f"✅ PDF Paper generated: {pdf_path}")
        except Exception as e:
            print(f"⚠️ PDF Export failed: {e}")

        # CLEANUP: Delete checkpoint
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()

        return paper

# Entry point for pipeline_service
async def main():
    orchestrator = AgentOrchestrator()
    return await orchestrator.run_pipeline()
