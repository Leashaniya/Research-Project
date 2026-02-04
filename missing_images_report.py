"""
Detailed report of questions that should have images but are represented
by semantic descriptions/text instead.
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = PROJECT_ROOT / "data" / "outputs"
PAPER_PATH = OUTPUTS_DIR / "model_papers" / "agentic_model_paper.json"

def generate_detailed_report():
    """Generate a detailed report of missing images"""
    
    paper = json.loads(PAPER_PATH.read_text())
    questions = paper.get("questions", [])
    
    print("="*80)
    print("DETAILED ANALYSIS: QUESTIONS WITH MISSING IMAGES")
    print("="*80)
    print(f"\nPaper Generated: {paper.get('generated_at', 'Unknown')}")
    print(f"Total Questions: {len(questions)}\n")
    
    missing_count = 0
    
    for q in questions:
        q_no = q.get("question_no", "?")
        q_text = q.get("text", "")
        subquestions = q.get("subquestions", [])
        topic = q.get("topic_label") or q.get("main_topic", "Unknown")
        
        # Check if should have image
        should_have = False
        reasons = []
        
        all_text = q_text + " " + " ".join([sq.get("text", "") for sq in subquestions])
        all_text_lower = all_text.lower()
        
        # Check for explicit diagram requests
        if "draw" in all_text_lower and ("er" in all_text_lower or "diagram" in all_text_lower or "schema" in all_text_lower):
            should_have = True
            reasons.append("Explicitly asks to draw a diagram")
        
        if "following" in all_text_lower and ("eer" in all_text_lower or "er diagram" in all_text_lower):
            should_have = True
            reasons.append("References a diagram that should be shown")
        
        if "convert" in all_text_lower and ("eer" in all_text_lower or "er diagram" in all_text_lower):
            should_have = True
            reasons.append("Asks to convert a diagram (implies diagram should exist)")
        
        # Check what it actually has
        has_image = q.get("diagram_generated") or q.get("diagram_image_path") or q.get("diagram_image_url")
        has_placeholder = bool(q.get("diagram_placeholder"))
        needs_diagram = q.get("needs_diagram", False)
        
        if should_have and not has_image:
            missing_count += 1
            
            print("-"*80)
            print(f"QUESTION {q_no} ({topic})")
            print("-"*80)
            print(f"\nWhy it should have an image:")
            for reason in reasons:
                print(f"  • {reason}")
            
            print(f"\nCurrent representation (SEMANTIC DESCRIPTION):")
            print(f"  Main Question Text:")
            print(f"    \"{q_text}\"")
            
            if subquestions:
                print(f"\n  Subquestions that reference diagrams:")
                for sq in subquestions:
                    sq_text = sq.get("text", "")
                    if any(word in sq_text.lower() for word in ["draw", "diagram", "convert", "following", "eer", "er diagram"]):
                        print(f"    ({sq.get('label', '?')}) \"{sq_text}\"")
            
            print(f"\n  What's missing:")
            if has_placeholder:
                print(f"    - Has placeholder text: {q.get('diagram_placeholder', 'N/A')}")
            elif needs_diagram:
                print(f"    - Marked as 'needs_diagram' but no image generated")
            else:
                print(f"    - No image reference at all")
                print(f"    - No placeholder text")
                print(f"    - Only semantic description in text")
            
            print(f"\n  Expected image type:")
            if "er" in all_text_lower or "eer" in all_text_lower:
                print(f"    - ER/EER Diagram showing entities, relationships, and attributes")
            elif "functional dependency" in all_text_lower or "fd" in all_text_lower:
                print(f"    - Functional Dependency Diagram")
            elif "schema" in all_text_lower:
                print(f"    - Relational Schema Diagram")
            else:
                print(f"    - Diagram/Visual representation")
            
            print(f"\n  Semantic meaning currently used instead:")
            # Extract semantic information from text
            entities = []
            relationships = []
            attributes = []
            
            # Simple extraction (could be improved)
            if "student" in all_text_lower:
                entities.append("Student")
            if "course" in all_text_lower:
                entities.append("Course")
            if "enrollment" in all_text_lower:
                entities.append("Enrollment")
            if "professor" in all_text_lower:
                entities.append("Professor")
            if "book" in all_text_lower or "inventory" in all_text_lower:
                entities.append("BookInventory")
            
            if entities:
                print(f"    - Entities: {', '.join(entities)}")
            if "many-to-many" in all_text_lower or "multiple" in all_text_lower:
                print(f"    - Relationships: Described textually (e.g., 'many-to-many')")
            if "primary key" in all_text_lower or "foreign key" in all_text_lower:
                print(f"    - Keys: Described textually (e.g., 'StudentID (primary key)')")
            
            print()
    
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\nTotal questions analyzed: {len(questions)}")
    print(f"Questions that should have images: {missing_count}")
    print(f"\n[KEY FINDING]")
    print(f"  {missing_count} out of {len(questions)} questions ({missing_count*100//len(questions)}%)")
    print(f"  are represented by semantic descriptions/text instead of actual images.")
    print(f"\n  These questions describe:")
    print(f"  - Entity relationships (textually)")
    print(f"  - Attributes and keys (textually)")
    print(f"  - Diagram structures (textually)")
    print(f"\n  Instead of showing:")
    print(f"  - Visual ER/EER diagrams")
    print(f"  - Functional dependency diagrams")
    print(f"  - Schema diagrams")
    print("="*80 + "\n")

if __name__ == "__main__":
    generate_detailed_report()
