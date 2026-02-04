"""
Refined analysis: Distinguish between questions that need to SHOW a diagram
vs questions that ask students to DRAW a diagram themselves.
"""
import json
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUTS_DIR = PROJECT_ROOT / "data" / "outputs"
PAPER_PATH = OUTPUTS_DIR / "model_papers" / "agentic_model_paper.json"

def analyze_question_needs_image(q):
    """
    Determine if a question needs to SHOW an image (not just ask student to draw).
    Returns: (needs_image, reason, evidence)
    """
    q_text = q.get("text", "")
    subquestions = q.get("subquestions", [])
    all_text = q_text + " " + " ".join([sq.get("text", "") for sq in subquestions])
    all_text_lower = all_text.lower()
    
    # PATTERN 1: Check FIRST if student is asked to draw (does NOT need image shown)
    # This must be checked BEFORE reference patterns to avoid false positives
    # "Draw an ER diagram" - student creates it
    # "Sketch a diagram" - student creates it
    # BUT: If main question asks to draw, and later parts reference "the diagram",
    #      that's referring to what student drew, not something that needs to be shown
    
    # Check if main question asks student to draw
    # Pattern: "Draw an Entity-Relationship Diagram" or "Draw an ER diagram"
    main_q_draws = bool(re.search(r"draw\s+(?:an?\s+)?(?:eer|er|entity[\s-]?relationship|entity[\s-]relationship\s+diagram)", q_text.lower()))
    
    if main_q_draws:
        # If main question asks to draw, then any "convert the diagram" references
        # are referring to what student drew, not something that needs to be shown
        return False, "Main question asks student to draw diagram (no image needed)", "student_draws"
    
    # Also check subquestions - if a subquestion asks to draw, and later parts reference it,
    # that's still student work, not something to show
    for sq in subquestions:
        sq_text = sq.get("text", "").lower()
        if re.search(r"draw\s+(?:an?\s+)?(?:eer|er|diagram)", sq_text):
            # Check if later parts reference "the diagram" - if so, it's what student drew
            sq_idx = subquestions.index(sq)
            later_text = " ".join([s.get("text", "").lower() for s in subquestions[sq_idx+1:]])
            if re.search(r"convert\s+(?:the\s+)?(?:eer|er|diagram)", later_text):
                return False, "Subquestion asks student to draw, later parts convert it (no image needed)", "student_draws_then_converts"
    
    student_draw_patterns = [
        r"draw\s+(?:the\s+)?(?:functional\s+dependency|fd)\s+diagram",
        r"sketch\s+(?:an?\s+)?(?:eer|er|diagram|schema)",
        r"create\s+(?:an?\s+)?(?:eer|er|diagram|schema)",
        r"design\s+(?:an?\s+)?(?:eer|er|diagram|schema)",
        r"construct\s+(?:an?\s+)?(?:eer|er|diagram|schema)",
    ]
    
    # Check if it's asking student to draw (no image needed)
    for pattern in student_draw_patterns:
        if re.search(pattern, all_text_lower):
            return False, "Asks student to draw/create diagram (no image needed)", pattern
    
    # PATTERN 2: References an existing diagram that should be shown
    # "Convert the following EER model" - implies diagram should be shown
    # "Based on the diagram above/below" - implies diagram should be shown
    # BUT: Only if NOT preceded by student being asked to draw
    reference_patterns = [
        r"following\s+(?:eer|er|diagram|schema|figure|model)",
        r"given\s+(?:eer|er|diagram|schema|figure|model)",
        r"shown\s+(?:in\s+)?(?:the\s+)?(?:eer|er|diagram|schema|figure)",
        r"above\s+(?:eer|er|diagram|schema|figure)",
        r"below\s+(?:eer|er|diagram|schema|figure)",
        r"convert\s+(?:the\s+)?(?:following\s+)?(?:eer|er|diagram|model)",
        r"map\s+(?:the\s+)?(?:following\s+)?(?:eer|er|diagram|model)",
        r"transform\s+(?:the\s+)?(?:following\s+)?(?:eer|er|diagram|model)",
        r"based\s+on\s+(?:the\s+)?(?:eer|er|diagram|schema|figure)",
    ]
    
    for pattern in reference_patterns:
        match = re.search(pattern, all_text_lower)
        if match:
            # Check if this comes AFTER a "draw" instruction
            match_pos = match.start()
            before_text = all_text_lower[:match_pos]
            if not re.search(r"draw\s+(?:an?\s+)?(?:eer|er|entity[\s-]?relationship|diagram)", before_text):
                return True, "References existing diagram that should be shown", pattern
    
    return False, "No clear indication that image should be shown", None

def refined_analysis():
    """Refined analysis distinguishing showing vs drawing"""
    print("="*80)
    print("REFINED ANALYSIS: Questions That Need to SHOW Images")
    print("="*80)
    
    paper = json.loads(PAPER_PATH.read_text())
    questions = paper.get("questions", [])
    
    print(f"\nPaper Generated: {paper.get('generated_at', 'Unknown')}")
    print(f"Total Questions: {len(questions)}\n")
    
    needs_image = []
    student_draws = []
    
    for q in questions:
        q_no = q.get("question_no", "?")
        q_text = q.get("text", "")
        subquestions = q.get("subquestions", [])
        topic = q.get("topic_label") or q.get("main_topic", "Unknown")
        
        needs_img, reason, evidence = analyze_question_needs_image(q)
        
        # Check what it actually has
        has_image = q.get("diagram_generated") or q.get("diagram_image_path") or q.get("diagram_image_url")
        
        if needs_img:
            needs_image.append({
                "question": q_no,
                "topic": topic,
                "reason": reason,
                "evidence": evidence,
                "has_image": has_image,
                "text": q_text[:150] + "..."
            })
        elif "draw" in reason.lower() or "create" in reason.lower():
            student_draws.append({
                "question": q_no,
                "topic": topic,
                "reason": reason,
                "text": q_text[:150] + "..."
            })
    
    # Print results
    print("="*80)
    print("QUESTIONS THAT NEED TO SHOW AN IMAGE")
    print("="*80)
    
    if needs_image:
        print(f"\nCount: {len(needs_image)}")
        for item in needs_image:
            print(f"\n- Question {item['question']} ({item['topic']})")
            print(f"  Reason: {item['reason']}")
            print(f"  Evidence: {item['evidence']}")
            print(f"  Has image: {'YES' if item['has_image'] else 'NO - MISSING'}")
            print(f"  Text: {item['text']}")
    else:
        print("\n[RESULT] No questions need to show an image.")
        print("All diagram-related questions ask students to draw/create them.")
    
    print("\n" + "="*80)
    print("QUESTIONS THAT ASK STUDENTS TO DRAW (No image needed)")
    print("="*80)
    
    if student_draws:
        print(f"\nCount: {len(student_draws)}")
        for item in student_draws:
            print(f"\n- Question {item['question']} ({item['topic']})")
            print(f"  Reason: {item['reason']}")
            print(f"  Text: {item['text']}")
    
    # Summary
    missing_count = sum(1 for item in needs_image if not item['has_image'])
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\nTotal questions: {len(questions)}")
    print(f"Questions that need to SHOW an image: {len(needs_image)}")
    print(f"  - Actually have images: {len(needs_image) - missing_count}")
    print(f"  - Missing images: {missing_count}")
    print(f"\nQuestions that ask students to DRAW: {len(student_draws)}")
    
    if missing_count > 0:
        print(f"\n[KEY FINDING]")
        print(f"  {missing_count} question(s) need to show an image but are")
        print(f"  represented only by semantic descriptions/text.")
    else:
        print(f"\n[KEY FINDING]")
        print(f"  All questions that need images have them, OR")
        print(f"  they correctly ask students to draw diagrams themselves.")
    
    print("="*80 + "\n")

if __name__ == "__main__":
    refined_analysis()
