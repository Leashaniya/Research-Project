"""
Test template selection diversity to ensure Q1 and Q2 select different templates.
"""
import sys
import asyncio
from pathlib import Path

# Add backend to path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    sys.path.append(str(project_root / "backend"))

# Handle Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from app.agents.orchestrator import AgentOrchestrator
from app.core.db import db

async def test_template_selection_diversity():
    """Test that template selection ensures diversity across slots."""
    print("="*70)
    print("TESTING TEMPLATE SELECTION DIVERSITY")
    print("="*70)
    
    # Initialize DB
    db.connect()
    
    try:
        orchestrator = AgentOrchestrator()
        
        # Simulate selecting templates for Q1, Q2, Q3, Q4
        slots = [
            {"question_no": "Q1", "target_marks": 20, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 15, "topics": ["General"]},
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 40, "topics": ["General"]}
        ]
        
        used_modules = set()
        used_intents = set()
        used_template_ids = set()
        
        selected_templates = []
        
        print("\nSimulating template selection for 4 slots...")
        print("-"*70)
        
        for slot in slots:
            q_no = slot["question_no"]
            target_marks = slot["target_marks"]
            
            # Get canonical template first
            canonical = await orchestrator._get_canonical_template(q_no)
            
            # Select template (same logic as in run_pipeline)
            if isinstance(canonical, dict) and "subquestion_structure" in canonical:
                canonical_intent = canonical.get("dominant_topic", "General")
                canonical_id = str(canonical.get("_id", ""))
                
                # Check if canonical template is already used (BEFORE using it)
                canonical_intent_used = canonical_intent in used_intents
                canonical_id_used = canonical_id in used_template_ids if canonical_id else False
                
                if canonical_intent_used and canonical_id_used:
                    print(f"\n{q_no}: Canonical template already used, searching for alternative...")
                    template = await orchestrator._select_template(q_no, target_marks, used_modules, used_intents, used_template_ids)
                else:
                    template = {
                        "pattern_label": canonical_intent,
                        "full_text": f"Reference: {canonical.get('source_paper', 'Unknown')}",
                        "marks": canonical.get("total_marks", target_marks),
                        "required_structure": canonical.get("subquestion_structure", []),
                        "_id": canonical.get("_id")
                    }
                    # Don't add to sets here - will be added after logging
            else:
                template = canonical if canonical else await orchestrator._select_template(q_no, target_marks, used_modules, used_intents, used_template_ids)
            
            # Get template info BEFORE tracking (for accurate logging)
            template_id = str(template.get("_id", ""))
            template_intent = template.get("pattern_label", "General")
            
            # Check if already used (BEFORE adding to sets)
            was_intent_used = template_intent in used_intents
            was_template_id_used = template_id in used_template_ids if template_id else False
            
            print(f"\n{q_no} ({target_marks} marks):")
            print(f"  Template ID: {template_id if template_id else 'N/A (canonical)'}")
            print(f"  Intent: {template_intent}")
            print(f"  Already Used Intent: {'Yes [WARN]' if was_intent_used else 'No [OK]'}")
            print(f"  Already Used Template ID: {'Yes [WARN]' if was_template_id_used else 'No [OK]'}")
            
            # Track template (AFTER logging)
            if template_id and template_id not in used_template_ids:
                used_template_ids.add(template_id)
            if template_intent and template_intent not in used_intents:
                used_intents.add(template_intent)
            
            selected_templates.append({
                "slot": q_no,
                "template_id": template_id if template_id else "N/A (canonical)",
                "intent": template_intent,
                "marks": target_marks
            })
        
        print("\n" + "="*70)
        print("DIVERSITY ANALYSIS")
        print("="*70)
        
        # Check for duplicate template IDs
        template_ids = [t["template_id"] for t in selected_templates if t["template_id"] != "N/A (canonical)"]
        unique_template_ids = set(template_ids)
        duplicate_ids = [tid for tid in template_ids if template_ids.count(tid) > 1]
        
        # Check for duplicate intents
        intents = [t["intent"] for t in selected_templates]
        unique_intents = set(intents)
        duplicate_intents = [intent for intent in intents if intents.count(intent) > 1]
        
        print(f"\nTemplate ID Diversity:")
        print(f"  Total selections: {len(selected_templates)}")
        print(f"  Unique template IDs: {len(unique_template_ids)}")
        if duplicate_ids:
            print(f"  [FAIL] Duplicate template IDs found: {set(duplicate_ids)}")
            for dup_id in set(duplicate_ids):
                slots_with_dup = [t["slot"] for t in selected_templates if t["template_id"] == dup_id]
                print(f"    - Template ID {dup_id} used in: {', '.join(slots_with_dup)}")
        else:
            print(f"  [PASS] All template IDs are unique")
        
        print(f"\nIntent Diversity:")
        print(f"  Total selections: {len(selected_templates)}")
        print(f"  Unique intents: {len(unique_intents)}")
        print(f"  Intent list: {', '.join(sorted(unique_intents))}")
        if duplicate_intents:
            print(f"  [WARN] Duplicate intents found: {set(duplicate_intents)}")
            for dup_intent in set(duplicate_intents):
                slots_with_dup = [t["slot"] for t in selected_templates if t["intent"] == dup_intent]
                print(f"    - Intent '{dup_intent}' used in: {', '.join(slots_with_dup)}")
        else:
            print(f"  [PASS] All intents are unique")
        
        # Final verdict
        print("\n" + "="*70)
        if duplicate_ids:
            print("[FAIL] Template selection diversity test FAILED")
            print("Some slots selected the same template ID.")
            return False
        elif duplicate_intents:
            print("[WARN] Template selection diversity test PASSED with warnings")
            print("All template IDs are unique, but some intents are repeated.")
            print("This is acceptable if no better alternatives exist.")
            return True
        else:
            print("[PASS] Template selection diversity test PASSED")
            print("All slots selected unique templates with unique intents.")
            return True
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    success = asyncio.run(test_template_selection_diversity())
    sys.exit(0 if success else 1)

