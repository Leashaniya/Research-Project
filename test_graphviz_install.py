"""
Test Graphviz installation and diagram generation
"""
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.semantic_diagram_service import SemanticDiagramService
from app.core.paths import OUTPUTS_DIR

def test_graphviz_finding():
    """Test if Graphviz can be found"""
    print("="*70)
    print("Testing Graphviz Installation")
    print("="*70)
    
    service = SemanticDiagramService()
    dot_path = service._find_graphviz_dot()
    
    if dot_path:
        print(f"\n[OK] Graphviz found at: {dot_path}")
        return True
    else:
        print("\n[ERROR] Graphviz not found")
        print("\nNote: Graphviz was installed but PATH may need to be refreshed.")
        print("Please restart your terminal/shell and try again.")
        print("\nOr manually add Graphviz bin directory to PATH:")
        print("  1. Find Graphviz installation (usually in Program Files)")
        print("  2. Add the 'bin' folder to your PATH environment variable")
        return False

def test_diagram_generation():
    """Test diagram generation with Q1 description"""
    print("\n" + "="*70)
    print("Testing Diagram Generation")
    print("="*70)
    
    # Q1 description
    q1_description = """A university has a database that contains information about students, courses, and enrollments. 
    The students have attributes such as StudentID (primary key), Name, and Age. 
    The courses have attributes like CourseID (primary key), CourseName, and Credits. 
    An enrollment connects students to courses and includes attributes EnrollmentID (primary key), Grade, and Semester. 
    There are many students for each course (many-to-many relationship), and a student can be enrolled in multiple courses."""
    
    service = SemanticDiagramService()
    
    print("\n1. Testing semantic parsing...")
    try:
        parsed = service.parse_semantic_description(q1_description)
        print(f"   [OK] Parsed {len(parsed.get('entities', []))} entities")
        print(f"   [OK] Parsed {len(parsed.get('relationships', []))} relationships")
    except Exception as e:
        print(f"   [ERROR] Parsing failed: {e}")
        return False
    
    print("\n2. Testing Graphviz code generation...")
    try:
        dot_code = service.generate_graphviz_code(parsed, diagram_type="EER")
        print(f"   [OK] Generated Graphviz DOT code ({len(dot_code)} characters)")
    except Exception as e:
        print(f"   [ERROR] Code generation failed: {e}")
        return False
    
    print("\n3. Testing image rendering...")
    output_path = OUTPUTS_DIR / "model_papers" / "images" / "test_q1_diagram.png"
    try:
        result = service.generate_diagram_from_semantic_description(
            description=q1_description,
            output_path=output_path,
            diagram_type="EER",
            format="png"
        )
        
        if result.get("success"):
            print(f"   [OK] Success! Diagram saved to: {result['image_path']}")
            return True
        else:
            print(f"   [ERROR] Rendering failed: {result.get('error')}")
            return False
    except Exception as e:
        print(f"   [ERROR] Error: {e}")
        return False

if __name__ == "__main__":
    graphviz_found = test_graphviz_finding()
    
    if graphviz_found:
        test_diagram_generation()
    else:
        print("\n[WARN] Cannot test diagram generation without Graphviz.")
        print("Please restart your terminal and run this test again.")
    
    print("\n" + "="*70)
