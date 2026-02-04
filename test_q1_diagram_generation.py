"""
Test Q1 diagram generation - simulates what happens during paper generation
"""
import sys
from pathlib import Path
import json

backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.semantic_diagram_service import SemanticDiagramService
from app.core.paths import OUTPUTS_DIR

print("="*70)
print("TESTING Q1 DIAGRAM GENERATION")
print("="*70)

# Simulate Q1 semantic description (what would be in the generated question)
q1_semantic_description = """
A university database contains information about students, courses, and enrollments.

Entities:
- Student: StudentID (primary key), Name, Age, Email
- Course: CourseID (primary key), CourseName, Credits, Department
- Enrollment: EnrollmentID (primary key), Grade, Semester, Year

Relationships:
- Student enrolls in Course (many-to-many relationship)
- Enrollment connects Student and Course

ISA Hierarchies:
- GraduateStudent is a subtype of Student (with additional attributes: ThesisTitle, AdvisorName)
- UndergraduateStudent is a subtype of Student (with additional attributes: Major, GPA)
- PartTimeCourse is a subtype of Course (with additional attributes: EveningSchedule)
- FullTimeCourse is a subtype of Course (with additional attributes: DaySchedule)
"""

print("\n[STEP 1] Initializing Semantic Diagram Service...")
try:
    service = SemanticDiagramService()
    print("   [OK] Service initialized")
except Exception as e:
    print(f"   [ERROR] Failed to initialize service: {e}")
    sys.exit(1)

print("\n[STEP 2] Checking Graphviz installation...")
dot_path = service._find_graphviz_dot()
if not dot_path or not Path(dot_path).exists():
    print("   [ERROR] Graphviz not found!")
    print("   Please ensure Graphviz is installed and in PATH")
    sys.exit(1)
print(f"   [OK] Graphviz found: {dot_path}")

print("\n[STEP 3] Parsing semantic description (GPT-4)...")
print("   [INFO] This will call OpenAI API to parse the description...")
try:
    parsed_data = service.parse_semantic_description(q1_semantic_description)
    
    if not parsed_data:
        print("   [ERROR] Parsing returned empty result")
        sys.exit(1)
    
    entities = parsed_data.get("entities", [])
    relationships = parsed_data.get("relationships", [])
    isa_hierarchies = parsed_data.get("isa_hierarchies", [])
    
    print(f"   [OK] Parsed successfully:")
    print(f"      - Entities: {len(entities)}")
    print(f"      - Relationships: {len(relationships)}")
    print(f"      - ISA Hierarchies: {len(isa_hierarchies)}")
    
    # Show some details
    if entities:
        print(f"\n   [DETAILS] Sample entities:")
        for entity in entities[:3]:
            print(f"      - {entity.get('name', 'Unknown')}: {len(entity.get('attributes', []))} attributes")
    
except Exception as e:
    print(f"   [ERROR] Parsing failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[STEP 4] Generating Graphviz DOT code...")
try:
    dot_code = service.generate_graphviz_code(parsed_data, diagram_type="EER")
    
    if not dot_code or len(dot_code) < 50:
        print("   [ERROR] Generated DOT code is too short or empty")
        sys.exit(1)
    
    print(f"   [OK] Generated DOT code ({len(dot_code)} characters)")
    print(f"\n   [PREVIEW] First 200 characters of DOT code:")
    print("   " + "-"*60)
    for line in dot_code.split("\n")[:10]:
        print(f"   {line}")
    print("   " + "-"*60)
    
except Exception as e:
    print(f"   [ERROR] DOT code generation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[STEP 5] Rendering diagram to PNG image...")
try:
    # Create output directory
    images_dir = OUTPUTS_DIR / "model_papers" / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = images_dir / "test_Q1_EER_diagram.png"
    
    print(f"   [INFO] Output path: {output_path}")
    
    result = service.generate_diagram_from_semantic_description(
        description=q1_semantic_description,
        output_path=output_path,
        diagram_type="EER",
        format="png"
    )
    
    if result.get("success"):
        image_path = result.get("image_path")
        if image_path and Path(image_path).exists():
            file_size = Path(image_path).stat().st_size
            print(f"   [OK] Diagram generated successfully!")
            print(f"   [INFO] File: {image_path}")
            print(f"   [INFO] Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
            print(f"\n   [SUCCESS] Image generation test PASSED!")
        else:
            print(f"   [ERROR] Image file not found at: {image_path}")
            sys.exit(1)
    else:
        error_msg = result.get("error", "Unknown error")
        print(f"   [ERROR] Image generation failed: {error_msg}")
        sys.exit(1)
        
except Exception as e:
    print(f"   [ERROR] Rendering failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*70)
print("TEST SUMMARY")
print("="*70)
print("[SUCCESS] All steps completed successfully!")
print("\nThe diagram generation system is ready for paper generation.")
print("When Q1 is generated, it will automatically:")
print("  1. Detect that it needs a diagram")
print("  2. Parse the semantic description")
print("  3. Generate Graphviz diagram")
print("  4. Save it to the images folder")
print("  5. Reference it in the generated paper")
print("\nYou can now proceed with full paper generation.")
print("="*70)
