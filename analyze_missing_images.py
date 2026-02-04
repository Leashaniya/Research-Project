"""
Analyze the generated model paper to identify questions that should have images
but are currently represented only by semantic descriptions.
"""
import json
from pathlib import Path
import re

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = PROJECT_ROOT / "data" / "outputs"
PAPER_PATH = OUTPUTS_DIR / "model_papers" / "agentic_model_paper.json"

def should_have_image(question_text, subquestions):
    """
    Determine if a question should have an image based on keywords and context.
    Returns: (bool, str) - (should_have_image, reason)
    """
    text_lower = question_text.lower()
    
    # Check subquestions too
    all_text = question_text
    for sq in subquestions:
        all_text += " " + sq.get("text", "")
    
    all_text_lower = all_text.lower()
    
    # Keywords that indicate a diagram/image should be present
    diagram_keywords = [
        "draw", "sketch", "illustrate", "diagram", "figure", "visual",
        "er diagram", "eer diagram", "entity-relationship", 
        "relational schema", "schema diagram", "table structure",
        "functional dependency", "fd diagram", "normalization",
        "tree", "index", "b-tree", "graph", "flowchart",
        "architecture", "block diagram", "network diagram"
    ]
    
    # Check for explicit requests to draw/create diagrams
    draw_patterns = [
        r"draw\s+(?:an?\s+)?(?:er|eer|entity[\s-]?relationship|relational|schema|functional\s+dependency|fd|normalization|tree|index|graph|flowchart|diagram)",
        r"sketch\s+(?:an?\s+)?(?:er|eer|diagram|schema)",
        r"illustrate\s+(?:with\s+)?(?:an?\s+)?(?:er|eer|diagram|schema)",
        r"show\s+(?:an?\s+)?(?:er|eer|diagram|schema|figure)",
        r"create\s+(?:an?\s+)?(?:er|eer|diagram|schema)",
        r"design\s+(?:an?\s+)?(?:er|eer|diagram|schema)",
        r"construct\s+(?:an?\s+)?(?:er|eer|diagram|schema)",
    ]
    
    # Check for references to existing diagrams/figures
    reference_patterns = [
        r"following\s+(?:er|eer|diagram|schema|figure|table)",
        r"given\s+(?:er|eer|diagram|schema|figure|table)",
        r"shown\s+(?:in\s+)?(?:the\s+)?(?:er|eer|diagram|schema|figure)",
        r"above\s+(?:er|eer|diagram|schema|figure)",
        r"below\s+(?:er|eer|diagram|schema|figure)",
    ]
    
    # Check for diagram-related tasks
    task_patterns = [
        r"convert\s+(?:the\s+)?(?:er|eer|diagram)",
        r"map\s+(?:the\s+)?(?:er|eer|diagram)",
        r"transform\s+(?:the\s+)?(?:er|eer|diagram)",
        r"based\s+on\s+(?:the\s+)?(?:er|eer|diagram|schema|figure)",
    ]
    
    # Check if question explicitly asks to draw something
    for pattern in draw_patterns:
        if re.search(pattern, all_text_lower):
            return True, f"Contains draw/create request: '{pattern}'"
    
    # Check if question references a diagram that should exist
    for pattern in reference_patterns:
        if re.search(pattern, all_text_lower):
            return True, f"References existing diagram: '{pattern}'"
    
    # Check if question involves diagram conversion/mapping
    for pattern in task_patterns:
        if re.search(pattern, all_text_lower):
            return True, f"Involves diagram conversion: '{pattern}'"
    
    # Check for keyword matches (but prioritize explicit draw requests)
    for keyword in diagram_keywords:
        if keyword in all_text_lower:
            # Check if it's in a subquestion that asks to draw
            keyword_pos = all_text_lower.find(keyword)
            context_before = all_text_lower[max(0, keyword_pos-100):keyword_pos]
            # If "draw" appears near the keyword, it's already covered by draw_patterns
            if "draw" not in context_before.lower():
                return True, f"Contains diagram keyword: '{keyword}'"
    
    return False, "No diagram indicators found"

def analyze_paper():
    """Analyze the generated paper for missing images"""
    print("="*70)
    print("ANALYZING GENERATED MODEL PAPER FOR MISSING IMAGES")
    print("="*70)
    
    if not PAPER_PATH.exists():
        print(f"\n[ERROR] Paper not found: {PAPER_PATH}")
        return
    
    paper = json.loads(PAPER_PATH.read_text())
    questions = paper.get("questions", [])
    
    print(f"\n[INFO] Total questions in paper: {len(questions)}")
    print(f"[INFO] Paper generated at: {paper.get('generated_at', 'Unknown')}")
    
    missing_images = []
    has_images = []
    unclear_cases = []
    
    for q in questions:
        q_no = q.get("question_no", "?")
        q_text = q.get("text", "")
        subquestions = q.get("subquestions", [])
        topic = q.get("topic_label") or q.get("main_topic") or "Unknown"
        
        # Check if question should have an image
        should_have, reason = should_have_image(q_text, subquestions)
        
        # Check what the question actually has
        has_diagram_generated = q.get("diagram_generated", False)
        has_diagram_path = bool(q.get("diagram_image_path"))
        has_diagram_url = bool(q.get("diagram_image_url"))
        has_placeholder = bool(q.get("diagram_placeholder"))
        needs_diagram = q.get("needs_diagram", False)
        diagram_type = q.get("diagram_type")
        
        # Determine status
        has_actual_image = has_diagram_generated or has_diagram_path or has_diagram_url
        
        if should_have:
            if has_actual_image:
                has_images.append({
                    "question": q_no,
                    "topic": topic,
                    "reason": reason,
                    "has_image": True,
                    "diagram_type": diagram_type,
                    "path": q.get("diagram_image_path", "N/A")
                })
            elif has_placeholder or needs_diagram:
                missing_images.append({
                    "question": q_no,
                    "topic": topic,
                    "reason": reason,
                    "status": "placeholder_only",
                    "diagram_type": diagram_type,
                    "placeholder": q.get("diagram_placeholder", "N/A")
                })
            else:
                missing_images.append({
                    "question": q_no,
                    "topic": topic,
                    "reason": reason,
                    "status": "no_reference",
                    "diagram_type": diagram_type,
                    "text_sample": q_text[:100] + "..."
                })
        else:
            # Question doesn't need an image, but check if it has one anyway
            if has_actual_image:
                unclear_cases.append({
                    "question": q_no,
                    "topic": topic,
                    "has_image": True,
                    "reason": "Image present but question doesn't require it"
                })
    
    # Print results
    print("\n" + "="*70)
    print("RESULTS")
    print("="*70)
    
    print(f"\n[QUESTIONS THAT SHOULD HAVE IMAGES]")
    print(f"   Total: {len(missing_images) + len(has_images)}")
    print(f"   - With actual images: {len(has_images)}")
    print(f"   - Missing images (text only): {len(missing_images)}")
    
    if missing_images:
        print(f"\n[MISSING IMAGES - REPLACED WITH SEMANTIC MEANING]")
        print(f"   Count: {len(missing_images)}")
        print(f"\n   Details:")
        for i, item in enumerate(missing_images, 1):
            print(f"\n   {i}. Question {item['question']} ({item['topic']})")
            print(f"      Reason: {item['reason']}")
            print(f"      Status: {item['status']}")
            if item.get('diagram_type'):
                print(f"      Expected type: {item['diagram_type']}")
            if item.get('placeholder'):
                print(f"      Placeholder text: {item['placeholder'][:80]}...")
            elif item.get('text_sample'):
                print(f"      Question text: {item['text_sample']}")
    
    if has_images:
        print(f"\n[QUESTIONS WITH ACTUAL IMAGES]")
        print(f"   Count: {len(has_images)}")
        for item in has_images:
            print(f"   - {item['question']}: {item['diagram_type']} at {item['path']}")
    
    if unclear_cases:
        print(f"\n[UNCLEAR CASES]")
        print(f"   Count: {len(unclear_cases)}")
        for item in unclear_cases:
            print(f"   - {item['question']}: {item['reason']}")
    
    # Summary statistics
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"\nTotal questions analyzed: {len(questions)}")
    print(f"Questions that should have images: {len(missing_images) + len(has_images)}")
    print(f"  - Actually have images: {len(has_images)}")
    print(f"  - Missing images (semantic text only): {len(missing_images)}")
    print(f"\n[KEY FINDING]")
    print(f"   {len(missing_images)} questions are represented by semantic")
    print(f"   descriptions/text instead of actual images.")
    
    # Breakdown by status
    if missing_images:
        placeholder_count = sum(1 for m in missing_images if m['status'] == 'placeholder_only')
        no_ref_count = sum(1 for m in missing_images if m['status'] == 'no_reference')
        print(f"\n   Breakdown:")
        print(f"   - Have placeholder text: {placeholder_count}")
        print(f"   - No image reference at all: {no_ref_count}")
    
    print("="*70 + "\n")
    
    return {
        "total_questions": len(questions),
        "should_have_images": len(missing_images) + len(has_images),
        "has_images": len(has_images),
        "missing_images": len(missing_images),
        "missing_details": missing_images
    }

if __name__ == "__main__":
    analyze_paper()
