import time
import json
from pathlib import Path
from app.agents import BlueprintAnalyst, ContentResearcher, QuestionWriter, QualityCritic
from app.services.pdf_service import PDFService
import random
from app.core.paths import OUTPUTS_DIR, ARTIFACTS_DIR

# Config
MAX_RETRIES = 1  # How many times to rewrite a question if Critic rejects it

from app.core.db import db

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
        
        # MongoDB Connection
        self.db = db.get_db()

    async def _get_canonical_template(self, q_no):
        """Get the canonical template for a question position."""
        # Query MongoDB
        # q_no might be "Q1" or "1"
        q_str = str(q_no).replace("Q", "")
        
        canonical = await self.db.canonical_templates.find_one({"position_id": f"Q{q_str}"})
        if canonical:
             return canonical
             
        # Try raw ID match
        canonical = await self.db.canonical_templates.find_one({"position_id": q_str})
        if canonical:
            return canonical

        print(f"⚠️ No canonical template for {q_no}, using fallback")
        return await self._select_template(q_no, None)
    
    async def _select_template(self, q_no, marks):
        """Pick a random template from DB."""
        # Only consider templates with text
        # Using aggregation for random sample
        pipeline = [
            { "$match": { "full_text": { "$exists": True, "$ne": "" } } },
            { "$sample": { "size": 1 } }
        ]
        
        # Try specific match first
        q_num_str = str(q_no).replace("Q", "")
        match_query = { "question_id": q_num_str, "full_text": { "$exists": True } }
        
        cursor = self.db.templates.aggregate([
            { "$match": match_query },
            { "$sample": { "size": 1 } }
        ])
        
        results = await cursor.to_list(length=1)
        if results:
            return results[0]
            
        # Fallback: Match by marks
        if marks:
            cursor = self.db.templates.aggregate([
                { "$match": { 
                    "full_text": { "$exists": True },
                    "marks": { "$gte": int(marks)-5, "$lte": int(marks)+5 }
                }},
                { "$sample": { "size": 1 } }
            ])
            results = await cursor.to_list(length=1)
            if results:
                return results[0]

        # Final Fallback: Any template
        cursor = self.db.templates.aggregate(pipeline)
        results = await cursor.to_list(length=1)
        if results:
            return results[0]
            
        return {
             "pattern_label": "General Theory",
             "full_text": "(Reference style only) Explain the concept of X.",
             "marks": marks
        }

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
        total_marks = sum(int(q.get("marks") or 0) for q in final_questions)
        
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
            canonical = await self._get_canonical_template(q_no)
            
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
                template = canonical if canonical else await self._select_template(q_no, target_marks)
            
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
                    "template": template,
                    "q_no": q_no  # Pass q_no to fix "None" label
                })
                
                is_approved = review.get("approved", True) # Fallback to True if key missing
                
                if is_approved:
                    print(f"✅ {q_no} Approved!")
                    approved = True
                    break
                else:
                    feedback = review.get("feedback", "No feedback")
                    print(f"❌ {q_no} Rejected. Feedback: {feedback}")
                    
                    # IF it is a MATH ERROR, fallback immediately (no retries)
                    if "MATH ERROR" in feedback.upper():
                        print(f"🛑 Math mismatch detected. Skipping retries and applying fallback logic.")
                        break
            
            if not approved:
                print(f"⚠️ {q_no} forced approval after max retries. Applying STRICT TEMPLATE FALLBACK.")
                
                # FALLBACK: Force the draft to match the Template's structure exactly
                # This ensures marks sum up correctly (as they come from a real paper)
                
                # 1. Determine the source of truth for structure
                # 'required_structure' (Canonical) or 'subquestions' (Raw Template)
                struct_source = template.get("required_structure") or template.get("subquestions", [])
                
                if struct_source:
                    fallback_draft = {
                        "question_no": q_no,
                        "marks": target_marks,
                        "subquestions": []
                    }
                    
                    failed_sub_qs = draft.get("subquestions", [])
                    
                    # --- SCALING LOGIC ---
                    # 1. Calculate Template Total to see if we need to scale
                    template_total = sum(int(item.get("marks") or 0) for item in struct_source)
                    current_sum = 0
                    
                    # 2. Prepare the list
                    final_subqs = []
                    
                    for idx, item in enumerate(struct_source):
                        t_label = item.get("label", f"({idx+1})")
                        raw_t_marks = int(item.get("marks") or 0)
                        
                        # Scale marks if template differs from target
                        if template_total > 0 and template_total != target_marks:
                            # Proportional scaling
                            ratio = target_marks / template_total
                            new_marks = int(round(raw_t_marks * ratio))
                            # Ensure at least 1 mark if original had marks
                            if raw_t_marks > 0 and new_marks == 0:
                                new_marks = 1
                        else:
                            new_marks = raw_t_marks

                        salvaged_text = "..."
                        if idx < len(failed_sub_qs):
                            salvaged_text = failed_sub_qs[idx].get("text", "...")
                            
                        final_subqs.append({
                            "label": t_label,
                            "marks": new_marks,
                            "text": salvaged_text
                        })
                        current_sum += new_marks
                    
                    # 3. Fix Rounding Errors (Distribution of Remainder)
                    diff = int(target_marks) - int(current_sum)
                    if diff != 0 and final_subqs:
                        # Add/Subtract difference to the item with the most marks
                        max_idx = max(range(len(final_subqs)), key=lambda i: final_subqs[i]['marks'])
                        final_subqs[max_idx]['marks'] += diff
                        
                    fallback_draft["subquestions"] = final_subqs
                    
                    # Replace the failed draft with our mathematically correct fallback
                    draft = fallback_draft
                    print(f"  🔧 Fixed marks using template structure (Scaled {template_total} -> {target_marks})")
            
            # 2c. RENDER the question for final display
            draft["question_no"] = q_no
            draft["text"] = self._render_question(draft)
            
            final_questions.append(draft)
            total_marks += int(draft.get("marks") or 0)

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
        
        # Save to MongoDB
        try:
            await self.db.papers.insert_one(paper.copy()) # Copy because _id is added
            print("✅ Paper saved to MongoDB.")
        except Exception as e:
            print(f"⚠️ MongoDB Save failed: {e}")

        out_path = self.out_dir / "agentic_model_paper.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(paper, f, indent=2, default=str) # default=str for ObjectId
            
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
