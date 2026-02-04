"""
Test script for semantic diagram generation
"""
import json
from pathlib import Path
from backend.app.services.semantic_diagram_service import SemanticDiagramService
from backend.app.core.paths import OUTPUTS_DIR

def test_q1_diagram():
    """Test generating diagram for Q1"""
    print("="*70)
    print("Testing Semantic Diagram Generation for Q1")
    print("="*70)
    
    # Q1 description
    q1_description = """A university has a database that contains information about students, courses, and enrollments. 
    The students have attributes such as StudentID (primary key), Name, and Age. 
    The courses have attributes like CourseID (primary key), CourseName, and Credits. 
    An enrollment connects students to courses and includes attributes EnrollmentID (primary key), Grade, and Semester. 
    There are many students for each course (many-to-many relationship), and a student can be enrolled in multiple courses."""
    
    service = SemanticDiagramService()
    
    # Test parsing
    print("\n1. Testing semantic parsing...")
    parsed = service.parse_semantic_description(q1_description)
    print(f"   Entities found: {len(parsed.get('entities', []))}")
    for entity in parsed.get('entities', []):
        print(f"     - {entity.get('name')}: {entity.get('attributes')}")
    print(f"   Relationships found: {len(parsed.get('relationships', []))}")
    for rel in parsed.get('relationships', []):
        print(f"     - {rel.get('entity1')} <-> {rel.get('entity2')} ({rel.get('cardinality')})")
    
    # Test Graphviz generation
    print("\n2. Testing Graphviz code generation...")
    dot_code = service.generate_graphviz_code(parsed, diagram_type="EER")
    print(f"   Generated {len(dot_code.split(chr(10)))} lines of DOT code")
    print(f"   Preview (first 10 lines):")
    for line in dot_code.split("\n")[:10]:
        print(f"     {line}")
    
    # Test image generation
    print("\n3. Testing image rendering...")
    output_path = OUTPUTS_DIR / "model_papers" / "images" / "test_q1_diagram.png"
    result = service.generate_diagram_from_semantic_description(
        description=q1_description,
        output_path=output_path,
        diagram_type="EER",
        format="png"
    )
    
    if result.get("success"):
        print(f"   ✅ Success! Diagram saved to: {result['image_path']}")
        print(f"   Parsed data: {len(result['parsed_data'].get('entities', []))} entities")
    else:
        print(f"   ❌ Failed: {result.get('error')}")
        if result.get('dot_code'):
            print(f"   DOT code was generated but rendering failed")
            print(f"   Check if Graphviz is installed: dot --version")
    
    print("\n" + "="*70)

if __name__ == "__main__":
    test_q1_diagram()
