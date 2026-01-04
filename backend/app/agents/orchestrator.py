import time
import json
from pathlib import Path
from app.agents import BlueprintAnalyst, ContentResearcher, QuestionWriter, QualityCritic
from app.services.pdf_service import PDFService
import random
from app.core.paths import OUTPUTS_DIR, ARTIFACTS_DIR

# Config
MAX_RETRIES = 3  # How many times to rewrite a question if Critic rejects it

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

    def _simplify_template(self, template, target_marks):
        """
        Force-reduce templates with >7 sub-questions to exactly 7.
        Merges small questions to maintain mark total.
        Real-world papers can have up to 7 sub-questions if needed.
        """
        structure = template.get("required_structure") or template.get("subquestions", [])
        if not structure or len(structure) <= 7:
            return template

        print(f"    ✂️  Template too long ({len(structure)} parts). Simplifying to 7 parts...")
        
        # Sort by marks (preserve high-value questions)
        # Strategy: Keep top 6 biggest questions, merge the rest into a "Concepts" question
        # OR simple accumulation. Let's do simple accumulation to preserve order.
        
        new_structure = []
        current_part = {"label": "x", "marks": 0, "text": "Combined part"}
        
        # Calculate target per part (approx)
        total_marks = sum(int(s.get("marks",0)) for s in structure)
        
        # Create exactly 7 buckets (increased from 5 for realism)
        bucket_size = len(structure) / 7.0 
        
        # Group indices: 0,1 -> 0; 2,3 -> 1; etc.
        import math
        
        buckets = [[] for _ in range(7)]
        for i, item in enumerate(structure):
            bucket_idx = min(int(i // bucket_size), 6)
            buckets[bucket_idx].append(item)
            
        final_qs = []
        import string
        for idx, bucket in enumerate(buckets):
            if not bucket: continue
            
            # Sum marks
            m = sum(int(item.get("marks", 0)) for item in bucket)
            
            # Combine text descriptions (if any) or types
            # Heuristic: Use the type/label of the first item
            first = bucket[0]
            
            final_qs.append({
                "label": string.ascii_lowercase[idx],
                "marks": m,
                "type": first.get("type", "General"),
                "text": first.get("text", "...") # Preserve hint from first item
            })
            
        # Update template
        new_template = template.copy()
        new_template["required_structure"] = final_qs
        new_template["subquestions"] = final_qs
        
        return new_template

    def _render_question(self, draft):
        """Convert structured subquestions into a beautiful string."""
        main_q_no = draft.get("question_no", "?")
        sub_qs = draft.get("subquestions", [])
        
        if not sub_qs:
            return draft.get("text", "...")
            
        lines = []
        # Use sequential alphabetic labeling (a, b, c...) for total consistency
        import string
        for idx, sq in enumerate(sub_qs):
            # Determine label: use existing if it's a simple character, otherwise use index
            raw_label = str(sq.get("label", "")).strip().rstrip(").")
            if not raw_label or len(raw_label) > 1:
                label = string.ascii_lowercase[idx % 26]
            else:
                label = raw_label
                
            text = sq.get("text", "...")
            marks = sq.get("marks", 0)
            lines.append(f"{label}) {text} ({marks} marks)")
            
        return "\n".join(lines)

    def _validate_topic_coverage(self, questions):
        """
        Validates that the paper covers diverse topics and no single topic dominates.
        Real-world papers should have balanced topic distribution.
        """
        topic_marks = {}
        total_marks = 0
        
        for q in questions:
            # Extract main topic from pattern_label or main_topic
            topic = q.get("main_topic") or q.get("pattern_label", "General")
            marks = int(q.get("marks", 0))
            topic_marks[topic] = topic_marks.get(topic, 0) + marks
            total_marks += marks
        
        if total_marks == 0:
            return
        
        # Check if any single topic dominates (>40% of marks)
        max_topic_ratio = max((marks / total_marks) * 100 for marks in topic_marks.values())
        if max_topic_ratio > 40:
            print(f"⚠️  WARNING: Topic '{max(topic_marks.items(), key=lambda x: x[1])[0]}' dominates with {max_topic_ratio:.1f}% of marks")
            print(f"   Recommendation: Ensure better topic diversity (no topic should exceed 40%)")
        
        # Check topic diversity (should have at least 3 distinct topics for 5 questions)
        unique_topics = len(topic_marks)
        if unique_topics < 3 and len(questions) >= 5:
            print(f"⚠️  WARNING: Only {unique_topics} unique topics detected for {len(questions)} questions")
            print(f"   Recommendation: Ensure broader syllabus coverage")
        else:
            print(f"✅ Topic Coverage: {unique_topics} distinct topics covered")

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
        
        # Track already used content for uniqueness
        used_topics = set()
        used_scenarios = set()
        used_question_types = set() # Track structural types like 'er_diagram', 'sql_query'
        
        # Pre-populate based on checkpoint
        for q in final_questions:
            topic = q.get("main_topic")
            if topic: used_topics.add(topic)
            # Scenario tracking might be trickier from saved text, but we can try simple extraction
            # Or just rely on fresh generation for the rest
        
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
            
            # 2a.2 SIMPLIFY TEMPLATE (User Request: Realistic Flow)
            # If template has > 5 parts, crush it down to 5
            template = self._simplify_template(template, target_marks)

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
            
            # Identify forbidden topics for this specific slot
            forbidden_topics = []
            
            # --- STRICT ANTI-REPETITION LOGIC ---
            # If we already have an ER diagram, forbid another one
            if "er_diagram" in used_question_types:
                forbidden_topics.append("Draw an ER diagram")
                forbidden_topics.append("Draw an EER diagram")
            
            # If we already have ER → Relational Mapping, forbid another one
            if "er_to_relational_mapping" in used_question_types:
                forbidden_topics.append("Map the ER diagram to relational")
                forbidden_topics.append("Map ER to relational schema")
                forbidden_topics.append("Convert ER diagram to relational model")
                forbidden_topics.append("Design relational schema from ER diagram")
            
            # If we just asked about Normalization, restrict it
            if "normalization" in used_question_types:
                forbidden_topics.append("Normalization")
                
            print(f"    ⛔ Forbidden Topics: {forbidden_topics}")
            
            for attempt in range(MAX_RETRIES + 1):
                # Writer
                # Writer
                try:
                    draft = await self.writer.run({
                        "slot": slot,
                        "template": template,
                        "context": context,
                        "feedback": feedback,
                        "global_context": {
                            "used_topics": list(used_topics),
                            "used_scenarios": list(used_scenarios),
                            "forbidden_topics": forbidden_topics
                        }
                    })
                except Exception as e:
                    print(f"⚠️ Writer failed on attempt {attempt}: {e}. Retrying...")
                    feedback = f"Previous generation failed with error: {e}. Ensure all fields are filled."
                    continue
                
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
                    
                    # NORMALIZE LABELS (Strictly a, b, c...)
                    import string, re
                    for idx, sq in enumerate(draft.get("subquestions", [])):
                        sq["label"] = string.ascii_lowercase[idx % 26]
                        # Remove redundant label prefixes from text (e.g., "a) What is..." -> "What is...")
                        sq["text"] = re.sub(r"^\(?[a-iA-I]\)?[\.\)]\s*", "", sq.get("text", "")).strip()
                    
                    # Update global tracking: store topic and a snippet of the scenario
                    used_topics.add(template.get("pattern_label", "General"))
                    
                    # Detect Question Type from Text (Heuristic)
                    q_text_lower = draft.get("text", "").lower()
                    if ("draw" in q_text_lower or "design" in q_text_lower or "construct" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower):
                        used_question_types.add("er_diagram")
                        print("      📌 Marked type: er_diagram")
                    if "normalization" in q_text_lower or "normal form" in q_text_lower:
                        used_question_types.add("normalization")
                    if "write a query" in q_text_lower or "sql" in q_text_lower:
                        used_question_types.add("sql_query")
                    # Detect ER → Relational Mapping
                    if ("map" in q_text_lower or "convert" in q_text_lower or "transform" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower) and ("relational" in q_text_lower or "relational schema" in q_text_lower or "relational model" in q_text_lower):
                        used_question_types.add("er_to_relational_mapping")
                        print("      📌 Marked type: er_to_relational_mapping")
                    # Also detect "Design relational schema" as mapping (if ER mentioned in question)
                    if "design" in q_text_lower and "relational schema" in q_text_lower and ("er" in q_text_lower or "entity" in q_text_lower):
                        used_question_types.add("er_to_relational_mapping")
                        print("      📌 Marked type: er_to_relational_mapping")
                    
                    # Store a snippet of the scenario for global uniqueness
                    # Combine subquestion texts to get a good proxy for the scenario
                    scenario_proxy = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])])
                    if scenario_proxy:
                        used_scenarios.add(scenario_proxy[:200]) # Store first 200 chars as a signature
                    
                    break
                else:
                    feedback = review.get("feedback", "No feedback")
                    if isinstance(feedback, list):
                        feedback = "; ".join(feedback)
                    print(f"❌ {q_no} Rejected. Feedback: {feedback}")
                    
                    # IF it is a MATH ERROR, fallback immediately (no retries)
                    if "MATH ERROR" in feedback.upper():
                        print(f"🛑 Math mismatch detected. Skipping retries and applying fallback logic.")
                        break
            
            if not approved:
                # If it's a hallucination error, we should NOT force approve it as is.
                if feedback and "QUALITY ERROR" in feedback.upper():
                    print(f"🛑 {q_no} failed quality check after retries. Attempting to sanitize...")
                    # Basic sanitization: strip common hallucination placeholders
                    draft_json = json.dumps(draft)
                    hallucination_placeholders = ["[FIGURE: ...]", "[FIGURE]", "slide 22", "slide_22", "fig 1", "refer to diagram"]
                    for hp in hallucination_placeholders:
                        draft_json = draft_json.replace(hp, "(Diagram omitted - please refer to context)")
                    draft = json.loads(draft_json)
                
                if "MATH ERROR" in feedback.upper():
                     print(f"⚠️ {q_no} forced approval (Trigger: MATH ERROR). Applying STRICT TEMPLATE FALLBACK.")
                else:
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
                        import string, re
                        t_label = string.ascii_lowercase[idx % 26]
                        raw_t_marks = int(item.get("marks") or 0)
                        
                        # Scale marks if template differs from target
                        if template_total > 0 and template_total != target_marks:
                            ratio = target_marks / template_total
                            new_marks = int(round(raw_t_marks * ratio))
                            if raw_t_marks > 0 and new_marks == 0: new_marks = 1
                        else:
                            new_marks = raw_t_marks

                        salvaged_text = "..."
                        if idx < len(failed_sub_qs):
                            salvaged_text = failed_sub_qs[idx].get("text", "...")
                        
                        # Clean salvaged text
                        salvaged_text = re.sub(r"^\(?[a-iA-I]\)?[\.\)]\s*", "", salvaged_text).strip()
                        
                        # Improved fallback: Generate minimal viable question text instead of "..."
                        if not salvaged_text or salvaged_text == "..." or len(salvaged_text.strip()) < 10:
                            # Generate context-aware fallback based on structure type
                            struct_type = item.get("type", "concept")
                            pattern_label = template.get("pattern_label", "Database Systems")
                            
                            if "er" in struct_type.lower() or "diagram" in struct_type.lower():
                                salvaged_text = f"Construct an ER/EER diagram for the scenario described above, showing all entities, relationships, and attributes."
                            elif "normalize" in struct_type.lower() or "normal" in struct_type.lower():
                                salvaged_text = f"Normalize the given relation schema to the appropriate normal form, showing all steps."
                            elif "sql" in struct_type.lower() or "query" in struct_type.lower():
                                salvaged_text = f"Write SQL queries to perform the required operations on the database schema."
                            elif "define" in struct_type.lower() or "explain" in struct_type.lower():
                                salvaged_text = f"Define and explain the key concepts related to {pattern_label}."
                            else:
                                salvaged_text = f"Explain {struct_type if struct_type != 'General' else pattern_label} in the context of the scenario above."
                            
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
            
            # --- IMPORTANT: UPDATE GLOBAL TRACKING FOR FORCED APPROVAL ---
            # Even if forced, we must record what we used so Q2, Q3 know about it
            used_topics.add(template.get("pattern_label", "General"))
            
            # Detect Question Type (Heuristic) for Forced Approval
            q_text_lower = draft.get("text", "").lower()
            if ("draw" in q_text_lower or "design" in q_text_lower or "construct" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower):
                used_question_types.add("er_diagram")
                print("      📌 Marked type: er_diagram (Forced)")
            if "normalization" in q_text_lower or "normal form" in q_text_lower:
                used_question_types.add("normalization")
            if "write a query" in q_text_lower or "sql" in q_text_lower:
                used_question_types.add("sql_query")
            # Detect ER → Relational Mapping (Forced Approval)
            if ("map" in q_text_lower or "convert" in q_text_lower or "transform" in q_text_lower) and ("er diagram" in q_text_lower or "eer diagram" in q_text_lower) and ("relational" in q_text_lower or "relational schema" in q_text_lower or "relational model" in q_text_lower):
                used_question_types.add("er_to_relational_mapping")
                print("      📌 Marked type: er_to_relational_mapping (Forced)")
            if "design" in q_text_lower and "relational schema" in q_text_lower and ("er" in q_text_lower or "entity" in q_text_lower):
                used_question_types.add("er_to_relational_mapping")
                print("      📌 Marked type: er_to_relational_mapping (Forced)")

            # Store Scenario for Forced Approval
            scenario_proxy = " ".join([sq.get("text", "") for sq in draft.get("subquestions", [])])
            if scenario_proxy:
                used_scenarios.add(scenario_proxy[:200])
            
            # 2c. RENDER the question for final display
            draft["question_no"] = q_no
            draft["text"] = self._render_question(draft)
            
            final_questions.append(draft)
            total_marks += int(draft.get("marks") or 0)

            # SAVE CHECKPOINT
            with open(self.checkpoint_path, "w", encoding="utf-8") as f:
                json.dump({"questions": final_questions}, f, indent=2)

        # 3. VALIDATE TOPIC COVERAGE
        self._validate_topic_coverage(final_questions)
        
        # 4. SAVE
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
