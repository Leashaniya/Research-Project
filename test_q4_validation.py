"""
Test script to validate Q4 generation and check nested items format
"""
import asyncio
import sys
import json
from pathlib import Path

# Handle Windows terminal encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set up project root and Python path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.append(str(PROJECT_ROOT / "backend"))

async def test_q4_validation():
    """Run pipeline and validate Q4 structure"""
    print("\n" + "="*70)
    print("Q4 VALIDATION TEST - Checking Fallback & Nested Items Format")
    print("="*70 + "\n")
    
    from app.agents.orchestrator import AgentOrchestrator
    from app.core.db import db
    
    try:
        # Initialize DB
        db.connect()
        
        # Run Orchestrator
        orchestrator = AgentOrchestrator()
        paper = await orchestrator.run_pipeline()
        
        # Extract Q4
        q4 = None
        for q in paper.get("questions", []):
            if q.get("question_no", "").upper() in ["Q4", "4"]:
                q4 = q
                break
        
        if not q4:
            print("❌ ERROR: Q4 not found in generated paper!")
            return False
        
        print("\n" + "="*70)
        print("Q4 VALIDATION RESULTS")
        print("="*70)
        
        # Check if it's a fallback
        is_fallback = "(Fallback)" in q4.get("text", "") or q4.get("text", "").startswith("(Fallback)")
        print(f"\n1. FALLBACK STATUS: {'❌ YES - Q4 is a fallback' if is_fallback else '✅ NO - Q4 was properly generated'}")
        
        # Check structure
        subquestions = q4.get("subquestions", [])
        print(f"\n2. SUBQUESTION COUNT: {len(subquestions)} (Expected: 3)")
        
        if len(subquestions) == 3:
            print("   ✅ Correct number of subquestions")
        else:
            print(f"   ❌ Wrong count! Expected 3, got {len(subquestions)}")
        
        # Check part (a) nested items
        part_a = subquestions[0] if subquestions else None
        if part_a:
            part_a_label = part_a.get("label", "").strip().lower()
            print(f"\n3. PART (a) ANALYSIS:")
            print(f"   Label: {part_a.get('label')}")
            print(f"   Text: {part_a.get('text', '')[:100]}...")
            
            nested_items = part_a.get("subquestions", [])
            print(f"   Nested items count: {len(nested_items)} (Expected: 3)")
            
            if len(nested_items) >= 3:
                print("   ✅ Has required nested items")
                
                # Check labels
                expected_labels = ["i", "ii", "iii"]
                actual_labels = [item.get("label", "").strip().lower() for item in nested_items[:3]]
                print(f"   Labels: {actual_labels} (Expected: {expected_labels})")
                
                if actual_labels == expected_labels:
                    print("   ✅ Labels match past paper format")
                else:
                    print(f"   ❌ Labels don't match! Expected {expected_labels}, got {actual_labels}")
                
                # Check marks
                expected_marks = [4, 6, 7]
                actual_marks = [int(item.get("marks", 0)) for item in nested_items[:3]]
                print(f"   Marks: {actual_marks} (Expected: {expected_marks})")
                
                if actual_marks == expected_marks:
                    print("   ✅ Marks match past paper format")
                else:
                    print(f"   ❌ Marks don't match! Expected {expected_marks}, got {actual_marks}")
                
                # Check if they start with "Find"
                print(f"\n   NESTED ITEMS CONTENT:")
                for idx, item in enumerate(nested_items[:3]):
                    label = item.get("label", "?")
                    text = item.get("text", "")
                    marks = item.get("marks", 0)
                    starts_with_find = text.strip().lower().startswith("find")
                    
                    print(f"   {label}) [{marks} marks] {text[:80]}...")
                    if starts_with_find:
                        print(f"      ✅ Starts with 'Find' (correct for SQL queries)")
                    else:
                        print(f"      ❌ Does NOT start with 'Find' (should be SQL query)")
            else:
                print(f"   ❌ Missing nested items! Expected 3, got {len(nested_items)}")
        
        # Check parts (b) and (c)
        if len(subquestions) >= 2:
            part_b = subquestions[1]
            print(f"\n4. PART (b) ANALYSIS:")
            print(f"   Label: {part_b.get('label')}")
            print(f"   Marks: {part_b.get('marks')} (Expected: 11)")
            print(f"   Text: {part_b.get('text', '')[:100]}...")
            
            if part_b.get("marks") == 11:
                print("   ✅ Marks match past paper format")
            else:
                print(f"   ❌ Marks don't match! Expected 11, got {part_b.get('marks')}")
            
            has_function = "create a function" in part_b.get("text", "").lower() or "create function" in part_b.get("text", "").lower()
            if has_function:
                print("   ✅ Contains 'Create a function' (correct for part b)")
            else:
                print("   ⚠️  Does NOT contain 'Create a function' (may be incorrect)")
        
        if len(subquestions) >= 3:
            part_c = subquestions[2]
            print(f"\n5. PART (c) ANALYSIS:")
            print(f"   Label: {part_c.get('label')}")
            print(f"   Marks: {part_c.get('marks')} (Expected: 12)")
            print(f"   Text: {part_c.get('text', '')[:100]}...")
            
            if part_c.get("marks") == 12:
                print("   ✅ Marks match past paper format")
            else:
                print(f"   ❌ Marks don't match! Expected 12, got {part_c.get('marks')}")
            
            has_trigger = "create a trigger" in part_c.get("text", "").lower() or "create trigger" in part_c.get("text", "").lower()
            if has_trigger:
                print("   ✅ Contains 'Create a trigger' (correct for part c)")
            else:
                print("   ⚠️  Does NOT contain 'Create a trigger' (may be incorrect)")
        
        # Check total marks
        total_marks = q4.get("marks", 0)
        print(f"\n6. TOTAL MARKS: {total_marks} (Expected: 40)")
        if total_marks == 40:
            print("   ✅ Total marks correct")
        else:
            print(f"   ❌ Total marks incorrect! Expected 40, got {total_marks}")
        
        # Check schema format
        text = q4.get("text", "")
        has_schema_phrase = "consider the following schema" in text.lower()
        has_data_types = any(t in text.lower() for t in [": int", ": varchar", ": date"])
        has_table_descriptions = "table stores" in text.lower() or "table holds" in text.lower() or "table manages" in text.lower()
        
        print(f"\n7. SCHEMA FORMAT:")
        print(f"   Schema phrase: {'✅' if has_schema_phrase else '❌'}")
        print(f"   Data types: {'✅' if has_data_types else '❌'}")
        print(f"   Table descriptions: {'✅' if has_table_descriptions else '❌'}")
        
        print("\n" + "="*70)
        print("VALIDATION COMPLETE")
        print("="*70 + "\n")
        
        # Save Q4 to file for inspection
        output_file = PROJECT_ROOT / "q4_validation_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(q4, f, indent=2, ensure_ascii=False)
        print(f"✅ Q4 saved to: {output_file}")
        
        return True
    except Exception as e:
        print(f"\n[ERROR] Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_q4_validation())
