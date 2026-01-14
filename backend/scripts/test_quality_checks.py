"""
Test script to validate all quality checks implemented in the critic and orchestrator.

Tests:
1. Empty/placeholder detection
2. Duplicate subquestion detection
3. ER scenario requirement
4. Normalization schema requirement
5. Fallback validation
6. Marks validation
"""

import sys
import json
from pathlib import Path

# Add backend to path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    sys.path.append(str(project_root / "backend"))

from app.agents.critic import QualityCritic
from app.agents.orchestrator import AgentOrchestrator

def test_empty_placeholder():
    """Test that drafts with empty/placeholder content are rejected."""
    print("\n" + "="*70)
    print("TEST 1: Empty/Placeholder Detection")
    print("="*70)
    
    critic = QualityCritic()
    
    # Test case 1: Empty subquestion
    draft1 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Question about databases.",
        "subquestions": [
            {"label": "a", "text": "...", "marks": 10},
            {"label": "b", "text": "What is normalization?", "marks": 15}
        ]
    }
    
    # Test case 2: Placeholder text
    draft2 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Question about databases.",
        "subquestions": [
            {"label": "a", "text": "TBD", "marks": 10},
            {"label": "b", "text": "What is normalization?", "marks": 15}
        ]
    }
    
    # Test case 3: Empty stem
    draft3 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "...",
        "subquestions": [
            {"label": "a", "text": "What is a database?", "marks": 25}
        ]
    }
    
    template = {"pattern_label": "General", "required_structure": []}
    
    import asyncio
    async def run_test():
        result1 = await critic.run({"draft": draft1, "template": template, "context": ""})
        result2 = await critic.run({"draft": draft2, "template": template, "context": ""})
        result3 = await critic.run({"draft": draft3, "template": template, "context": ""})
        
        assert not result1.get("approved"), f"TEST 1.1 FAILED: Empty subquestion was approved. Result: {result1}"
        assert result1.get("feedback_code") == "EMPTY_SUBQUESTION", f"TEST 1.1: Wrong feedback code: {result1.get('feedback_code')}"
        print("✅ TEST 1.1 PASSED: Empty subquestion rejected")
        
        assert not result2.get("approved"), f"TEST 1.2 FAILED: Placeholder text was approved. Result: {result2}"
        assert result2.get("feedback_code") == "EMPTY_SUBQUESTION", f"TEST 1.2: Wrong feedback code: {result2.get('feedback_code')}"
        print("✅ TEST 1.2 PASSED: Placeholder text rejected")
        
        assert not result3.get("approved"), f"TEST 1.3 FAILED: Empty stem was approved. Result: {result3}"
        assert result3.get("feedback_code") == "EMPTY_STEM", f"TEST 1.3: Wrong feedback code: {result3.get('feedback_code')}"
        print("✅ TEST 1.3 PASSED: Empty stem rejected")
    
    asyncio.run(run_test())

def test_duplicate_subquestions():
    """Test that duplicate/near-duplicate subquestions are rejected."""
    print("\n" + "="*70)
    print("TEST 2: Duplicate Subquestion Detection")
    print("="*70)
    
    critic = QualityCritic()
    
    # Test case 1: Exact duplicate (after normalization)
    draft1 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Question about databases.",
        "subquestions": [
            {"label": "a", "text": "What is normalization?", "marks": 10},
            {"label": "b", "text": "What is normalization?", "marks": 15}
        ]
    }
    
    # Test case 2: High similarity
    draft2 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Question about databases.",
        "subquestions": [
            {"label": "a", "text": "What is normalization and why is it important?", "marks": 10},
            {"label": "b", "text": "What is normalization and why is it important for databases?", "marks": 15}
        ]
    }
    
    template = {"pattern_label": "General", "required_structure": []}
    
    import asyncio
    async def run_test():
        result1 = await critic.run({"draft": draft1, "template": template, "context": ""})
        result2 = await critic.run({"draft": draft2, "template": template, "context": ""})
        
        assert not result1.get("approved"), f"TEST 2.1 FAILED: Duplicate subquestions were approved. Result: {result1}"
        assert result1.get("feedback_code") == "DUPLICATE_SUBQUESTIONS", f"TEST 2.1: Wrong feedback code: {result1.get('feedback_code')}"
        print("✅ TEST 2.1 PASSED: Exact duplicate rejected")
        
        assert not result2.get("approved"), f"TEST 2.2 FAILED: High similarity subquestions were approved. Result: {result2}"
        assert result2.get("feedback_code") == "DUPLICATE_SUBQUESTIONS", f"TEST 2.2: Wrong feedback code: {result2.get('feedback_code')}"
        print("✅ TEST 2.2 PASSED: High similarity rejected")
    
    asyncio.run(run_test())

def test_er_scenario_required():
    """Test that ER/EER questions require scenario in stem."""
    print("\n" + "="*70)
    print("TEST 3: ER Scenario Requirement")
    print("="*70)
    
    critic = QualityCritic()
    
    # Test case 1: ER question without scenario
    draft1 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Draw an ER diagram.",
        "subquestions": [
            {"label": "a", "text": "Identify entities.", "marks": 10},
            {"label": "b", "text": "Draw the diagram.", "marks": 15}
        ]
    }
    
    # Test case 2: ER question with scenario (should pass)
    draft2 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Consider a university database system. The system manages students, courses, and enrollments. Each student has a student ID, name, and email. Each course has a course code, title, and credits. Students enroll in courses, and each enrollment has a grade. Draw an ER diagram for this system.",
        "subquestions": [
            {"label": "a", "text": "Identify the main entities and their attributes.", "marks": 10},
            {"label": "b", "text": "Draw the ER diagram showing relationships.", "marks": 15}
        ]
    }
    
    template1 = {"pattern_label": "ER Diagrams", "required_structure": []}
    template2 = {"pattern_label": "ER Diagrams", "required_structure": []}
    
    import asyncio
    async def run_test():
        result1 = await critic.run({"draft": draft1, "template": template1, "context": ""})
        result2 = await critic.run({"draft": draft2, "template": template2, "context": ""})
        
        assert not result1.get("approved"), f"TEST 3.1 FAILED: ER question without scenario was approved. Result: {result1}"
        assert result1.get("feedback_code") == "SCENARIO_MISSING", f"TEST 3.1: Wrong feedback code: {result1.get('feedback_code')}"
        print("✅ TEST 3.1 PASSED: ER question without scenario rejected")
        
        assert result2.get("approved"), f"TEST 3.2 FAILED: ER question with scenario was rejected. Result: {result2}"
        print("✅ TEST 3.2 PASSED: ER question with scenario approved")
    
    asyncio.run(run_test())

def test_normalization_schema_required():
    """Test that Normalization questions require schema and FDs."""
    print("\n" + "="*70)
    print("TEST 4: Normalization Schema Requirement")
    print("="*70)
    
    critic = QualityCritic()
    
    # Test case 1: Normalization question without schema
    draft1 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Normalize the given relation.",
        "subquestions": [
            {"label": "a", "text": "Find the normal form.", "marks": 10},
            {"label": "b", "text": "Decompose to 3NF.", "marks": 15}
        ]
    }
    
    # Test case 2: Normalization question with schema (should pass)
    draft2 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Given a relation R(A, B, C, D) with functional dependencies: A → B, B → C, C → D. Normalize this relation.",
        "subquestions": [
            {"label": "a", "text": "Identify the normal form of R.", "marks": 10},
            {"label": "b", "text": "Decompose R to 3NF.", "marks": 15}
        ]
    }
    
    template1 = {"pattern_label": "Normalization", "required_structure": []}
    template2 = {"pattern_label": "Normalization", "required_structure": []}
    
    import asyncio
    async def run_test():
        result1 = await critic.run({"draft": draft1, "template": template1, "context": ""})
        result2 = await critic.run({"draft": draft2, "template": template2, "context": ""})
        
        assert not result1.get("approved"), f"TEST 4.1 FAILED: Normalization question without schema was approved. Result: {result1}"
        assert result1.get("feedback_code") == "SCHEMA_MISSING", f"TEST 4.1: Wrong feedback code: {result1.get('feedback_code')}"
        print("✅ TEST 4.1 PASSED: Normalization question without schema rejected")
        
        assert result2.get("approved"), f"TEST 4.2 FAILED: Normalization question with schema was rejected. Result: {result2}"
        print("✅ TEST 4.2 PASSED: Normalization question with schema approved")
    
    asyncio.run(run_test())

def test_marks_validation():
    """Test that marks validation works correctly."""
    print("\n" + "="*70)
    print("TEST 5: Marks Validation")
    print("="*70)
    
    critic = QualityCritic()
    
    # Test case 1: Marks don't sum correctly
    draft1 = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Question about databases.",
        "subquestions": [
            {"label": "a", "text": "What is a database?", "marks": 10},
            {"label": "b", "text": "What is normalization?", "marks": 10}  # Sum = 20, not 25
        ]
    }
    
    # Test case 2: Zero marks
    draft2 = {
        "question_no": "Q1",
        "marks": 0,
        "text": "Question about databases.",
        "subquestions": [
            {"label": "a", "text": "What is a database?", "marks": 25}
        ]
    }
    
    template = {"pattern_label": "General", "required_structure": []}
    
    import asyncio
    async def run_test():
        result1 = await critic.run({"draft": draft1, "template": template, "context": ""})
        result2 = await critic.run({"draft": draft2, "template": template, "context": ""})
        
        assert not result1.get("approved"), f"TEST 5.1 FAILED: Marks mismatch was approved. Result: {result1}"
        assert result1.get("feedback_code") == "MATH_ERROR", f"TEST 5.1: Wrong feedback code: {result1.get('feedback_code')}"
        print("✅ TEST 5.1 PASSED: Marks mismatch rejected")
        
        assert not result2.get("approved"), f"TEST 5.2 FAILED: Zero marks was approved. Result: {result2}"
        assert result2.get("feedback_code") in ["MARKS_ERROR", "MATH_ERROR"], f"TEST 5.2: Wrong feedback code: {result2.get('feedback_code')}"
        print("✅ TEST 5.2 PASSED: Zero marks rejected")
    
    asyncio.run(run_test())

def test_valid_draft():
    """Test that a valid draft is approved."""
    print("\n" + "="*70)
    print("TEST 6: Valid Draft Approval")
    print("="*70)
    
    critic = QualityCritic()
    
    # Valid draft
    draft = {
        "question_no": "Q1",
        "marks": 25,
        "text": "Consider a library database system. The system manages books, members, and loans. Each book has an ISBN, title, and author. Each member has a member ID, name, and email. Members borrow books, and each loan has a borrow date and return date.",
        "subquestions": [
            {"label": "a", "text": "Identify the main entities and their attributes.", "marks": 10},
            {"label": "b", "text": "Draw an ER diagram showing all relationships.", "marks": 15}
        ]
    }
    
    template = {"pattern_label": "ER Diagrams", "required_structure": []}
    
    import asyncio
    async def run_test():
        result = await critic.run({"draft": draft, "template": template, "context": ""})
        
        assert result.get("approved"), f"TEST 6 FAILED: Valid draft was rejected. Result: {result}"
        print("✅ TEST 6 PASSED: Valid draft approved")
    
    asyncio.run(run_test())

def test_er_scenario_bullet_format():
    """Test that ER scenario validation accepts bullet scenarios."""
    print("\n" + "="*70)
    print("TEST 7: ER Scenario Bullet Format Acceptance")
    print("="*70)
    
    critic = QualityCritic()
    
    # Test case: ER question with bullet-style scenario (should pass)
    draft = {
        "question_no": "Q1",
        "marks": 25,
        "text": "University Database System:\n• Students have ID, name, email\n• Courses have code, title, credits\n• Students enroll in courses with grades",
        "subquestions": [
            {"label": "a", "text": "Identify entities and attributes.", "marks": 10},
            {"label": "b", "text": "Draw ER diagram.", "marks": 15}
        ]
    }
    
    template = {"pattern_label": "ER Diagrams", "required_structure": []}
    
    import asyncio
    async def run_test():
        result = await critic.run({"draft": draft, "template": template, "context": ""})
        
        assert result.get("approved"), f"TEST 7 FAILED: Bullet scenario was rejected. Result: {result}"
        print("✅ TEST 7 PASSED: Bullet scenario accepted")
    
    asyncio.run(run_test())

def test_blueprint_repair_generic():
    """Test that blueprint repair fixes any slot with marks<=0 without Q1 special-case."""
    print("\n" + "="*70)
    print("TEST 8: Generic Blueprint Repair")
    print("="*70)
    
    from app.agents.analyst import BlueprintAnalyst
    
    analyst = BlueprintAnalyst()
    
    # Test case: Blueprint with Q2 having zero marks (not Q1)
    blueprint = {
        "exam_title": "Test Exam",
        "question_slots": [
            {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q2", "target_marks": 0, "topics": ["General"]},  # Invalid, not Q1
            {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
            {"question_no": "Q4", "target_marks": 25, "topics": ["General"]}
        ]
    }
    
    repaired = analyst._validate_blueprint(blueprint)
    
    # Check that Q2 was repaired (not just Q1)
    q2_slot = next((s for s in repaired["question_slots"] if s.get("question_no") == "Q2"), None)
    assert q2_slot is not None, "TEST 8 FAILED: Q2 slot missing after repair"
    assert q2_slot.get("target_marks", 0) > 0, f"TEST 8 FAILED: Q2 marks not repaired. Got: {q2_slot.get('target_marks')}"
    print(f"✅ TEST 8 PASSED: Q2 marks repaired to {q2_slot.get('target_marks')} (generic repair, not Q1-specific)")

def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("QUALITY CHECKS VALIDATION TEST SUITE")
    print("="*70)
    
    try:
        test_empty_placeholder()
        test_duplicate_subquestions()
        test_er_scenario_required()
        test_normalization_schema_required()
        test_marks_validation()
        test_valid_draft()
        test_er_scenario_bullet_format()
        test_blueprint_repair_generic()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED!")
        print("="*70)
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())

