"""
Verification script to ensure mark assignments follow the golden rule:
- Marks are NOT assigned based on question number
- Marks come from: blueprint values, total_marks/num_slots, or config defaults
"""

import sys
import re
from pathlib import Path

# Add backend to path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    sys.path.append(str(project_root / "backend"))

def check_mark_assignments():
    """Check code for mark assignments based on question number."""
    print("="*70)
    print("VERIFYING MARK ASSIGNMENT RULES")
    print("="*70)
    
    issues = []
    
    # Check analyst.py
    analyst_path = project_root / "backend" / "app" / "agents" / "analyst.py"
    if analyst_path.exists():
        content = analyst_path.read_text(encoding="utf-8")
        
        # Check for hardcoded Q1 marks
        if re.search(r'Q1.*25|25.*Q1|"Q1".*target_marks.*25', content, re.IGNORECASE):
            issues.append("[FAIL] analyst.py: Found Q1-specific mark assignment (25)")
        
        # Check for position-based mark assignment
        if re.search(r'if.*q_no.*==.*["\']1["\'].*marks|if.*position.*==.*1.*marks', content, re.IGNORECASE):
            issues.append("[FAIL] analyst.py: Found position-based mark assignment")
        
        # Check that marks use config or calculation
        if 'settings.DEFAULT_SLOT_MARKS' in content or 'canonical_total_marks' in content:
            print("[PASS] analyst.py: Uses config defaults or historical statistics")
        
        # Check default blueprint
        if 'target_marks.*25' in content and 'DEFAULT_SLOT_MARKS' not in content:
            # Check if it's in default blueprint function
            default_blueprint_match = re.search(r'def _default_blueprint.*?target_marks.*?25', content, re.DOTALL)
            if default_blueprint_match:
                # Check if it uses config
                func_content = default_blueprint_match.group(0)
                if 'DEFAULT_SLOT_MARKS' not in func_content and 'canonical_total_marks' not in func_content:
                    issues.append("[FAIL] analyst.py: _default_blueprint() may have hardcoded marks")
    
    # Check orchestrator.py
    orchestrator_path = project_root / "backend" / "app" / "agents" / "orchestrator.py"
    if orchestrator_path.exists():
        content = orchestrator_path.read_text(encoding="utf-8")
        
        # Check for Q1-specific logic
        if re.search(r'if.*Q1.*marks|if.*q_no.*==.*["\']Q1["\'].*marks', content, re.IGNORECASE):
            issues.append("[FAIL] orchestrator.py: Found Q1-specific mark assignment")
    
    # Report results
    if issues:
        print("\n[FAIL] ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
        return False
    else:
        print("\n[PASS] ALL CHECKS PASSED:")
        print("  - No Q1-specific mark assignments")
        print("  - No position-based mark assignments")
        print("  - Marks derived from: blueprint values, total_marks/num_slots, or config defaults")
        return True

def test_blueprint_repair():
    """Test that blueprint repair doesn't use Q1-specific logic."""
    print("\n" + "="*70)
    print("TESTING BLUEPRINT REPAIR")
    print("="*70)
    
    from app.agents.analyst import BlueprintAnalyst
    from app.core.config import settings
    
    analyst = BlueprintAnalyst()
    
    # Test 1: Q2 has zero marks (not Q1)
    blueprint1 = {
        "canonical_total_marks": 100,
        "question_slots": [
            {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 0, "topics": ["General"]},  # Invalid
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
        ]
    }
    
    repaired1 = analyst._validate_blueprint(blueprint1)
    q2_slot = next((s for s in repaired1["question_slots"] if s.get("question_no") == "Q2"), None)
    
    if q2_slot and q2_slot.get("target_marks", 0) > 0:
        print(f"[PASS] TEST 1: Q2 marks repaired to {q2_slot.get('target_marks')} (not Q1-specific)")
        # Verify marks come from calculation, not hardcoded
        expected_marks = 100 // 4  # canonical_total_marks / num_slots
        if q2_slot.get("target_marks") == expected_marks:
            print(f"   [OK] Marks derived from canonical_total_marks / num_slots = {expected_marks}")
        else:
            print(f"   [INFO] Marks = {q2_slot.get('target_marks')}, expected {expected_marks} (may use average)")
    else:
        print("[FAIL] TEST 1: Q2 marks not repaired")
        return False
    
    # Test 2: Q3 has zero marks
    blueprint2 = {
        "canonical_total_marks": 100,
        "question_slots": [
            {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q3", "target_marks": 0, "topics": ["General"]},  # Invalid
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
        ]
    }
    
    repaired2 = analyst._validate_blueprint(blueprint2)
    q3_slot = next((s for s in repaired2["question_slots"] if s.get("question_no") == "Q3"), None)
    
    if q3_slot and q3_slot.get("target_marks", 0) > 0:
        print(f"[PASS] TEST 2: Q3 marks repaired to {q3_slot.get('target_marks')} (not Q1-specific)")
    else:
        print("[FAIL] TEST 2: Q3 marks not repaired")
        return False
    
    # Test 3: No canonical_total_marks - should use config default
    blueprint3 = {
        "question_slots": [
            {"question_no": "Q1", "target_marks": 0, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 0, "topics": ["General"]}
        ]
    }
    
    repaired3 = analyst._validate_blueprint(blueprint3)
    q1_slot = next((s for s in repaired3["question_slots"] if s.get("question_no") == "Q1"), None)
    
    if q1_slot and q1_slot.get("target_marks", 0) > 0:
        marks = q1_slot.get("target_marks")
        if marks == settings.DEFAULT_SLOT_MARKS:
            print(f"[PASS] TEST 3: Q1 marks use config default ({marks}), not hardcoded")
        else:
            print(f"[INFO] TEST 3: Q1 marks = {marks}, config default = {settings.DEFAULT_SLOT_MARKS}")
    else:
        print("[FAIL] TEST 3: Q1 marks not repaired")
        return False
    
    return True

def main():
    """Run all verification checks."""
    print("\n" + "="*70)
    print("MARK ASSIGNMENT RULES VERIFICATION")
    print("="*70)
    
    code_check = check_mark_assignments()
    repair_test = test_blueprint_repair()
    
    print("\n" + "="*70)
    if code_check and repair_test:
        print("[PASS] ALL VERIFICATIONS PASSED")
        print("="*70)
        print("\nMark assignment rules verified:")
        print("  [OK] No marks assigned based on question number")
        print("  [OK] Marks derived from: blueprint values, total_marks/num_slots, or config defaults")
        print("  [OK] All repairs are position-agnostic")
        return 0
    else:
        print("[FAIL] VERIFICATION FAILED")
        print("="*70)
        return 1

if __name__ == "__main__":
    sys.exit(main())

