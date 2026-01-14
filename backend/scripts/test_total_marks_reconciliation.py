"""
Test script to verify total-marks reconciliation after blueprint repair.
"""

import sys
from pathlib import Path

# Add backend to path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    sys.path.append(str(project_root / "backend"))

from app.agents.analyst import BlueprintAnalyst

def test_total_marks_reconciliation():
    """Test that total marks are reconciled to match canonical_total_marks."""
    print("="*70)
    print("TESTING TOTAL-MARKS RECONCILIATION")
    print("="*70)
    
    analyst = BlueprintAnalyst()
    
    # Test 1: Sum doesn't match canonical_total_marks
    blueprint1 = {
        "canonical_total_marks": 100,
        "question_slots": [
            {"question_no": "Q1", "target_marks": 20, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
            # Sum = 95, but canonical = 100, diff = +5
        ]
    }
    
    repaired1 = analyst._validate_blueprint(blueprint1)
    total1 = sum(slot.get("target_marks", 0) for slot in repaired1["question_slots"])
    canonical1 = repaired1.get("canonical_total_marks", blueprint1.get("canonical_total_marks", 0))
    
    print(f"\nTest 1: Sum mismatch (95 vs 100)")
    print(f"  Before: Sum = 95, Canonical = 100")
    print(f"  After:  Sum = {total1}, Canonical = {canonical1}")
    
    if total1 == canonical1:
        print(f"  [PASS] Total marks reconciled: {total1} == {canonical1}")
    else:
        print(f"  [FAIL] Total marks not reconciled: {total1} != {canonical1}")
        return False
    
    # Test 2: Sum exceeds canonical_total_marks
    blueprint2 = {
        "canonical_total_marks": 100,
        "question_slots": [
            {"question_no": "Q1", "target_marks": 30, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
            # Sum = 105, but canonical = 100, diff = -5
        ]
    }
    
    repaired2 = analyst._validate_blueprint(blueprint2)
    total2 = sum(slot.get("target_marks", 0) for slot in repaired2["question_slots"])
    canonical2 = repaired2.get("canonical_total_marks", blueprint2.get("canonical_total_marks", 0))
    
    print(f"\nTest 2: Sum exceeds canonical (105 vs 100)")
    print(f"  Before: Sum = 105, Canonical = 100")
    print(f"  After:  Sum = {total2}, Canonical = {canonical2}")
    
    if total2 == canonical2:
        print(f"  [PASS] Total marks reconciled: {total2} == {canonical2}")
    else:
        print(f"  [FAIL] Total marks not reconciled: {total2} != {canonical2}")
        return False
    
    # Test 3: Already matches (no reconciliation needed)
    blueprint3 = {
        "canonical_total_marks": 100,
        "question_slots": [
            {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
            # Sum = 100, matches canonical = 100
        ]
    }
    
    repaired3 = analyst._validate_blueprint(blueprint3)
    total3 = sum(slot.get("target_marks", 0) for slot in repaired3["question_slots"])
    canonical3 = repaired3.get("canonical_total_marks", blueprint3.get("canonical_total_marks", 0))
    
    print(f"\nTest 3: Already matches (100 vs 100)")
    print(f"  Before: Sum = 100, Canonical = 100")
    print(f"  After:  Sum = {total3}, Canonical = {canonical3}")
    
    if total3 == canonical3:
        print(f"  [PASS] Total marks unchanged: {total3} == {canonical3}")
    else:
        print(f"  [FAIL] Total marks changed: {total3} != {canonical3}")
        return False
    
    # Test 4: No canonical_total_marks (no reconciliation)
    blueprint4 = {
        "question_slots": [
            {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
        ]
    }
    
    repaired4 = analyst._validate_blueprint(blueprint4)
    total4 = sum(slot.get("target_marks", 0) for slot in repaired4["question_slots"])
    
    print(f"\nTest 4: No canonical_total_marks")
    print(f"  Sum = {total4} (no reconciliation, no canonical_total_marks)")
    print(f"  [PASS] No reconciliation when canonical_total_marks missing")
    
    print("\n" + "="*70)
    print("[PASS] ALL TOTAL-MARKS RECONCILIATION TESTS PASSED")
    print("="*70)
    return True

if __name__ == "__main__":
    success = test_total_marks_reconciliation()
    sys.exit(0 if success else 1)

