import json
from pathlib import Path
from .base import BaseAgent
from app.core.paths import ARTIFACTS_DIR
from app.core.config import settings

class BlueprintAnalyst(BaseAgent):
    """
    The Blueprint Analyst Agent.
    Role: Analyze past papers to determine the exam structure (blueprint).
    """

    def __init__(self, config=None):
        super().__init__(name="Blueprint Analyst", config=config)
        self.blueprint_path = ARTIFACTS_DIR / "exam_blueprint_template.json"

    async def run(self, input_data: dict = None) -> dict:
        """
        Analyses the past papers (conceptually) and returns the Exam Blueprint.
        
        In this iteration, it loads the pre-generated blueprint from the 'structure_topics_template.py' script output.
        Future V2: This agent will dynamically use an LLM to read the PDFs and infer the structure on-the-fly.
        """
        self.log("Analyzing past papers to determine structure...")
        
        # logic to load existing blueprint or run the structure script
        if not self.blueprint_path.exists():
            self.log("Blueprint not found, triggering generation script...")
            # Ideally we would call the script logic here if it wasn't already run
            # For now, we assume the linear pipeline Step 3 has run or we mock it.
            # Returning a fallback/default blueprint if missing is safer for the agent.
            return self._default_blueprint()

        try:
            blueprint = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
            self.log("Blueprint loaded successfully.")
            
            # Validate blueprint integrity
            validated_blueprint = self._validate_blueprint(blueprint)
            return validated_blueprint
        except Exception as e:
            self.log(f"Error loading blueprint: {e}")
            return self._default_blueprint()
    
    def _validate_blueprint(self, blueprint: dict) -> dict:
        """
        Validates blueprint integrity using generic structure validation.
        
        GOLDEN RULE: Question number never decides topic. This validation only ensures
        structural integrity (marks, slot IDs). Topics emerge from past-paper data analysis,
        not from question position.
        
        Rules:
        - Ensures minimum number of slots (MIN_SLOTS)
        - Repairs any slot with marks <= 0 or missing marks (generic, not Q1-specific)
        - Regenerates slot IDs sequentially if missing/invalid
        - No question-number-specific logic (topics emerge from data, not position)
        """
        slots = blueprint.get("question_slots", [])
        
        # Check minimum slots requirement
        if len(slots) < settings.MIN_SLOTS:
            self.log(f"[WARN] Blueprint has {len(slots)} slots, minimum is {settings.MIN_SLOTS}. Using default blueprint.")
            return self._default_blueprint()
        
        if not slots:
            self.log("[WARN] Blueprint has no question slots. Using default blueprint.")
            return self._default_blueprint()
        
        # Calculate total marks from valid slots and blueprint total (if available)
        valid_marks_sum = sum(slot.get("target_marks", 0) for slot in slots if slot.get("target_marks", 0) > 0)
        invalid_slots = [slot for slot in slots if slot.get("target_marks", 0) <= 0]
        blueprint_total = blueprint.get("canonical_total_marks")  # From historical statistics
        
        # Repair invalid slots
        # GOLDEN RULE: Marks derived from blueprint values, total_marks/num_slots, or config defaults
        # NOT from question number/position
        has_invalid = len(invalid_slots) > 0
        repaired_slots = []
        
        for idx, slot in enumerate(slots):
            q_no = slot.get("question_no") or slot.get("slot_id")
            target_marks = slot.get("target_marks", 0)
            
            # Repair: If marks are 0 or missing
            if target_marks <= 0:
                repaired_marks = None
                
                # Priority 1: Use blueprint total marks (from historical statistics)
                if blueprint_total and blueprint_total > 0:
                    # Distribute evenly: total_marks / number_of_slots
                    repaired_marks = int(round(blueprint_total / len(slots)))
                    self.log(f"[WARN] Slot {q_no or f'#{idx+1}'} has invalid marks ({target_marks}). Structure repair: using blueprint total ({blueprint_total}) / slots ({len(slots)}) = {repaired_marks}.")
                
                # Priority 2: Use average from valid slots (proportional distribution)
                elif valid_marks_sum > 0 and len(slots) > len(invalid_slots):
                    avg_marks = valid_marks_sum / (len(slots) - len(invalid_slots))
                    repaired_marks = int(round(avg_marks))
                    self.log(f"[WARN] Slot {q_no or f'#{idx+1}'} has invalid marks ({target_marks}). Structure repair: using average from valid slots = {repaired_marks}.")
                
                # Priority 3: Use configurable default (not tied to slot ID)
                else:
                    repaired_marks = settings.DEFAULT_SLOT_MARKS
                    self.log(f"[WARN] Slot {q_no or f'#{idx+1}'} has invalid marks ({target_marks}). Structure repair: using configurable default = {repaired_marks}.")
                
                slot["target_marks"] = repaired_marks
                has_invalid = True
            
            # Ensure slot has valid ID
            if not q_no or q_no == "?":
                slot["question_no"] = f"Q{idx + 1}"
                slot["slot_id"] = f"Q{idx + 1}"
                has_invalid = True
            
            repaired_slots.append(slot)
        
        # Update blueprint
        blueprint["question_slots"] = repaired_slots
        total_marks = sum(slot.get("target_marks", 0) for slot in repaired_slots)
        
        # TOTAL-MARKS RECONCILIATION: Ensure sum matches canonical_total_marks
        # This prevents papers ending up with totals like 80, 95, 105 accidentally
        if blueprint_total and blueprint_total > 0:
            diff = blueprint_total - total_marks
            if diff != 0:
                self.log(f"[WARN] Total marks mismatch: sum={total_marks}, canonical={blueprint_total}, diff={diff}")
                
                # Distribute difference across slots
                # Strategy: Add/subtract to highest-mark slots or recently repaired ones
                if repaired_slots:
                    # Sort slots by marks (descending) to prioritize high-mark slots
                    sorted_slots = sorted(repaired_slots, key=lambda s: s.get("target_marks", 0), reverse=True)
                    
                    # Distribute difference
                    remaining_diff = diff
                    for slot in sorted_slots:
                        if remaining_diff == 0:
                            break
                        
                        current_marks = slot.get("target_marks", 0)
                        if remaining_diff > 0:
                            # Add marks (distribute to highest slots first)
                            slot["target_marks"] = current_marks + 1
                            remaining_diff -= 1
                        else:
                            # Subtract marks (from highest slots first, but ensure >= 1)
                            if current_marks > 1:
                                slot["target_marks"] = current_marks - 1
                                remaining_diff += 1
                    
                    # If still have remainder, adjust the first slot
                    if remaining_diff != 0 and repaired_slots:
                        repaired_slots[0]["target_marks"] += remaining_diff
                        if repaired_slots[0]["target_marks"] < 1:
                            repaired_slots[0]["target_marks"] = 1
                    
                    # Recalculate total
                    total_marks = sum(slot.get("target_marks", 0) for slot in repaired_slots)
                    self.log(f"[INFO] Total marks reconciled: {total_marks} (canonical: {blueprint_total})")
        
        # Log validation results
        if has_invalid:
            self.log(f"[WARN] Blueprint structure repaired. Total marks: {total_marks}, Slots: {len(repaired_slots)}")
        else:
            self.log(f"[OK] Blueprint validated. Total marks: {total_marks}, Slots: {len(repaired_slots)}")
        
        return blueprint

    def _default_blueprint(self):
        """
        Fallback blueprint if analysis fails.
        
        GOLDEN RULE: Marks are NOT assigned based on question number.
        Marks are derived from:
        1. Historical statistics (canonical_total_marks) - if available
        2. Even distribution: total_marks / number_of_slots
        3. Configurable defaults (DEFAULT_SLOT_MARKS) - not tied to slot ID
        
        All mark assignments are position-agnostic.
        """
        self.log("Using DEFAULT Blueprint fallback.")
        
        # Try to load blueprint to get canonical_total_marks (historical statistics)
        canonical_total_marks = None
        if self.blueprint_path.exists():
            try:
                existing_blueprint = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
                canonical_total_marks = existing_blueprint.get("canonical_total_marks")
            except Exception:
                pass
        
        num_slots = settings.MIN_SLOTS
        
        # Determine marks per slot (NOT based on question number)
        if canonical_total_marks and canonical_total_marks > 0:
            # Priority 1: Use historical statistics (even distribution)
            marks_per_slot = int(round(canonical_total_marks / num_slots))
            self.log(f"Using canonical_total_marks ({canonical_total_marks}) from historical statistics: {marks_per_slot} marks per slot")
        else:
            # Priority 2: Use configurable default (not tied to slot ID)
            marks_per_slot = settings.DEFAULT_SLOT_MARKS
            self.log(f"Using configurable default: {marks_per_slot} marks per slot")
        
        # Create slots with evenly distributed marks (derived from stats/config, not position)
        slots = []
        for idx in range(num_slots):
            slots.append({
                "question_no": f"Q{idx + 1}",  # Sequential ID only (identifier, not mark source)
                "target_marks": marks_per_slot,  # From stats/config, NOT from question number
                "topics": ["General"]
            })
        
        return {
            "exam_title": "Model Exam (Fallback)",
            "canonical_total_marks": canonical_total_marks or (marks_per_slot * num_slots),
            "question_slots": slots
        }
