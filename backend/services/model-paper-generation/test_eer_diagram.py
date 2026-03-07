from pathlib import Path

from app.services.semantic_diagram_service import SemanticDiagramService


def main() -> None:
    """
    Ad‑hoc script to generate ONLY an EER diagram image for testing
    the aggregation layout (dotted box + external relationship) without
    running the full model‑paper pipeline.
    """

    description = """
In a university management system, there are four main entities: Department, Course, Student, and Professor.

Each Department offers many Courses, and each Course belongs to exactly one Department.
Students enroll in the offerings of Courses within Departments.
Professors teach Courses.

Students are further specialized into GraduateStudent and UndergraduateStudent. GraduateStudent has
additional attributes such as ThesisTitle, AdvisorName, and ResearchArea. UndergraduateStudent has
additional attributes such as YearOfStudy, Major, and GPA. Student is the supertype in an ISA hierarchy
with GraduateStudent and UndergraduateStudent as subtypes.

The scenario should be modeled so that the relationship 'Offers' between Department and Course
acts as a single unit when relating to Students through an enrollment relationship.
"""

    output_path = (
        Path("data")
        / "outputs"
        / "model_papers"
        / "images"
        / "test_eer_aggregation.png"
    )

    service = SemanticDiagramService()
    result = service.generate_diagram_from_semantic_description(
        description=description,
        output_path=output_path,
        diagram_type="EER",
        format="png",
        requires_isa=True,
        requires_aggregation=True,
        aggregation_spec={
            "entities_inside_aggregation": ["Department", "Course"],
            "relationship_inside_aggregation": "Offers",
            "external_entity": "Student",
            "external_relationship": "Enrolls",
        },
    )

    print("Generation result:", result)
    print(f"Diagram saved to: {output_path}")


if __name__ == "__main__":
    main()

