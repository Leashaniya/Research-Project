import sys
sys.path.insert(0, "backend")

from app.services.semantic_diagram_service import SemanticDiagramService

svc = SemanticDiagramService()

parsed = {
  "entities": [
    {"name": "Employee", "attributes": ["EmpID (PK)", "Name"], "primary_key": "EmpID"},
    {"name": "Project", "attributes": ["ProjectID (PK)", "Title"], "primary_key": "ProjectID"},
    {"name": "Supervisor", "attributes": ["SupervisorID (PK)", "Name"], "primary_key": "SupervisorID"},
  ],
  "relationships": [
    {
      "name": "Work_On",
      "entity1": "Employee",
      "entity2": "Project",
      "cardinality": "many-to-many",
      "min1": 0, "max1": "N",
      "min2": 0, "max2": "N",
      "descriptive_attributes": []
    },
    {
      "name": "Managed_By",
      "entity1": "Supervisor",
      # Set the other endpoint to an internal entity; generator should reroute to R_Work_On
      "entity2": "Employee",
      "cardinality": "one-to-many",
      "min1": 1, "max1": "N",
      "min2": 0, "max2": "N",
      "descriptive_attributes": []
    }
  ],
  "isa_hierarchies": [],
  "weak_entities": [],
  "aggregations": [
    {
      "aggregate_id": "WorkOnAssignment",
      "primary_relationship": "Work_On",
      "internal_entities": ["Employee", "Project"],
      "internal_attributes": ["StartDate", "Role", "Duration"],
      "external_links": ["Managed_By"]
    }
  ]
}

dot = svc.generate_graphviz_code(parsed, diagram_type="EER")
print(dot)

assert "subgraph cluster_WorkOnAssignment" in dot
assert 'style="dashed"' in dot
assert "R_Work_On" in dot
assert "R_Work_On_StartDate" in dot and "R_Work_On_Role" in dot and "R_Work_On_Duration" in dot
assert "R_Managed_By" in dot

# Check reroute: Managed_By should connect to R_Work_On somewhere
if "R_Managed_By -> R_Work_On" not in dot and "R_Work_On -> R_Managed_By" not in dot:
    raise AssertionError("Secondary relationship was not rerouted to connect to the primary relationship diamond")

print("\n[OK] Aggregation smoke test passed")
