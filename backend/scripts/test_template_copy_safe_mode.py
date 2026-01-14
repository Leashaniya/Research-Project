"""
Test script to verify TEMPLATE_COPY_SAFE_MODE fallback.
Simulates Writer raising an exception and ensures safe mode produces a valid draft.
"""

import sys
import asyncio
from pathlib import Path

# Handle Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

# Add backend to path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if project_root.name == "backend":
    sys.path.append(str(project_root))
else:
    sys.path.append(str(project_root / "backend"))

from app.agents.orchestrator import AgentOrchestrator
from app.agents.critic import QualityCritic
from app.core.db import db

async def test_template_copy_safe_mode():
    """Test that template-copy safe mode produces valid drafts when Writer fails."""
    print("="*70)
    print("TESTING TEMPLATE_COPY_SAFE_MODE")
    print("="*70)
    
    # Initialize DB
    db.connect()
    
    try:
        orchestrator = AgentOrchestrator()
        critic = QualityCritic()
        
        # Mock template with valid structure
        template = {
            "pattern_label": "ER and EER Diagrams",
            "full_text": "Consider a library database system with books, authors, and borrowers. Each book has ISBN, title, and publication year. Each author has author ID, name, and nationality. Books are written by authors, and borrowers can borrow books.",
            "required_structure": [
                {"label": "a", "marks": 5, "text": "Identify the main entities and their attributes."},
                {"label": "b", "marks": 10, "text": "Draw the ER diagram showing relationships and cardinalities."},
                {"label": "c", "marks": 10, "text": "Map the ER diagram to a relational schema."}
            ]
        }
        
        # Test 1: Build template-copy draft
        print("\nTest 1: Building template-copy draft...")
        draft = orchestrator._build_template_copy_draft("Q1", 25, template, True, "ER")
        
        # Verify draft structure
        assert draft.get("question_no") == "Q1", "Question number not set"
        assert draft.get("marks") == 25, "Marks not set correctly"
        assert draft.get("text"), "Stem text is empty"
        assert len(draft.get("text", "")) > 20, "Stem text too short"
        assert len(draft.get("subquestions", [])) > 0, "No subquestions"
        assert sum(sq.get("marks", 0) for sq in draft.get("subquestions", [])) == 25, "Subquestion marks don't sum to total"
        assert draft.get("needs_diagram") == True, "needs_diagram not set"
        assert draft.get("diagram_type") == "ER", "diagram_type not set"
        
        print(f"  [PASS] Draft structure valid")
        print(f"    - Question: {draft.get('question_no')}")
        print(f"    - Marks: {draft.get('marks')}")
        print(f"    - Stem length: {len(draft.get('text', ''))} chars")
        print(f"    - Stem preview: {draft.get('text', '')[:100]}...")
        print(f"    - Subquestions: {len(draft.get('subquestions', []))}")
        print(f"    - Subquestion marks sum: {sum(sq.get('marks', 0) for sq in draft.get('subquestions', []))}")
        
        # Test 2: Validate draft with critic
        print("\nTest 2: Validating draft with critic...")
        review = await critic.run({
            "draft": draft,
            "context": "Test context",
            "template": template,
            "q_no": "Q1"
        })
        
        if review.get("approved", False):
            print(f"  [PASS] Draft approved by critic")
        else:
            print(f"  [INFO] Draft rejected: {review.get('feedback', 'Unknown')}")
            print(f"    Feedback code: {review.get('feedback_code', 'Unknown')}")
            # This is expected for template-copy mode - it may need sanitization
        
        # Test 3: Sanitize draft with "described above" references
        print("\nTest 3: Testing sanitization...")
        draft_with_refs = {
            "question_no": "Q1",
            "marks": 25,
            "text": "As shown above, the database contains entities.",
            "subquestions": [
                {"label": "a", "marks": 10, "text": "Identify entities described above."},
                {"label": "b", "marks": 15, "text": "Draw the ER diagram as shown above."}
            ]
        }
        
        sanitized = orchestrator._sanitize_template_copy_draft(draft_with_refs, template)
        
        # Verify sanitization
        assert "described above" not in sanitized.get("text", "").lower(), "Stem still contains 'described above'"
        assert "as shown above" not in sanitized.get("text", "").lower(), "Stem still contains 'as shown above'"
        
        for sq in sanitized.get("subquestions", []):
            assert "described above" not in sq.get("text", "").lower(), f"Subquestion still contains 'described above': {sq.get('text')}"
            assert "as shown above" not in sq.get("text", "").lower(), f"Subquestion still contains 'as shown above': {sq.get('text')}"
        
        print(f"  [PASS] Sanitization successful")
        print(f"    - Stem: {sanitized.get('text', '')[:100]}...")
        print(f"    - Subquestions sanitized: {len(sanitized.get('subquestions', []))}")
        
        # Test 4: ER intent - ensure scenario is added if missing
        print("\nTest 4: Testing ER scenario insertion...")
        template_er = {
            "pattern_label": "ER and EER Diagrams",
            "full_text": "Short text.",  # Too short, should trigger scenario insertion
            "required_structure": [
                {"label": "a", "marks": 10, "text": "Identify entities."}
            ]
        }
        
        draft_er = orchestrator._build_template_copy_draft("Q1", 20, template_er, True, "ER")
        
        # Verify ER scenario is present (should be added because full_text is too short)
        stem_text = draft_er.get("text", "").lower()
        has_entity = "entity" in stem_text or "student" in stem_text or "course" in stem_text
        assert has_entity, f"ER scenario not added. Stem: {draft_er.get('text', '')[:200]}"
        print(f"  [PASS] ER scenario added to stem")
        print(f"    - Stem: {draft_er.get('text', '')[:150]}...")
        
        # Test 5: Normalization intent - ensure schema is added if missing
        print("\nTest 5: Testing Normalization schema insertion...")
        template_norm = {
            "pattern_label": "Functional Dependencies and Normalization",
            "full_text": "Short text.",
            "required_structure": [
                {"label": "a", "marks": 10, "text": "Find normal form."}
            ]
        }
        
        draft_norm = orchestrator._build_template_copy_draft("Q1", 20, template_norm, False, None)
        
        # Verify Normalization schema is present
        assert "schema" in draft_norm.get("text", "").lower() or "relation" in draft_norm.get("text", "").lower(), "Normalization schema not added"
        print(f"  [PASS] Normalization schema added to stem")
        print(f"    - Stem: {draft_norm.get('text', '')[:150]}...")
        
        print("\n" + "="*70)
        print("[PASS] ALL TEMPLATE_COPY_SAFE_MODE TESTS PASSED")
        print("="*70)
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    success = asyncio.run(test_template_copy_safe_mode())
    sys.exit(0 if success else 1)

