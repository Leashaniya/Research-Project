"""
Test cardinality/participation constraints parsing and display
"""
import sys
from pathlib import Path

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.semantic_diagram_service import SemanticDiagramService

print("="*70)
print("TESTING CARDINALITY / PARTICIPATION CONSTRAINTS")
print("="*70)

# Test description with explicit participation constraints
test_description = """
A university database has the following entities and relationships:

Entities:
- Student: StudentID (PK), Name, Email
- Course: CourseID (PK), CourseName, Credits
- Instructor: InstructorID (PK), Name, Department

Relationships:
- Student enrolls in Course: Many-to-many relationship. A student can enroll in zero or more courses (0,N), and a course can have zero or more students (0,N).
- Instructor teaches Course: One-to-many relationship. An instructor can teach zero or more courses (0,N), but each course must have at least one instructor (1,N).
"""

print("\n[TEST] Parsing description with participation constraints...")
service = SemanticDiagramService()

try:
    parsed_data = service.parse_semantic_description(test_description)
    
    print(f"\n[RESULTS]")
    print(f"Entities: {len(parsed_data.get('entities', []))}")
    print(f"Relationships: {len(parsed_data.get('relationships', []))}")
    
    print(f"\n[RELATIONSHIPS WITH CARDINALITY]:")
    for i, rel in enumerate(parsed_data.get('relationships', []), 1):
        print(f"\nRelationship {i}:")
        print(f"  Name: {rel.get('name', 'N/A')}")
        print(f"  Entity1: {rel.get('entity1', 'N/A')}")
        print(f"  Entity2: {rel.get('entity2', 'N/A')}")
        print(f"  Cardinality: {rel.get('cardinality', 'N/A')}")
        print(f"  Participation Entity1: ({rel.get('min1', 0)},{rel.get('max1', 'N')})")
        print(f"  Participation Entity2: ({rel.get('min2', 0)},{rel.get('max2', 'N')})")
    
    # Test Graphviz code generation
    print(f"\n[TEST] Generating Graphviz code...")
    dot_code = service.generate_graphviz_code(parsed_data, diagram_type="ER")
    
    # Check if participation constraints are in the DOT code
    if "(0,N)" in dot_code or "(1,N)" in dot_code or "(0,1)" in dot_code or "(1,1)" in dot_code:
        print("[OK] Participation constraints found in DOT code")
        # Show relevant lines
        lines = dot_code.split('\n')
        for line in lines:
            if 'label=' in line and ('(' in line and ',' in line):
                print(f"  {line.strip()}")
    else:
        print("[WARN] Participation constraints NOT found in DOT code")
        print("Sample DOT code:")
        print(dot_code[:500])
        
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
