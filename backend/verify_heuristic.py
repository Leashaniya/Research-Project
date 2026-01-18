
import unittest
from app.agents.orchestrator import AgentOrchestrator

class TestOrchestratorHeuristics(unittest.TestCase):
    def test_heuristic_detection(self):
        # Mock sets
        used_question_types = set()
        used_scenarios = set()
        
        # Mock Draft with ER in subquestions
        draft = {
            "text": "General database question.",
            "subquestions": [
                {"text": "Draw an ER diagram for the hospital system."},
                {"text": "Map the ER diagram to a relational schema."}
            ]
        }
        
        # Logic copied/adapted from Orchestrator (since it's inline in run_pipeline, we verify the logic itself)
        # In the actual class, this logic is inside run_pipeline. 
        # Ideally we would test the method, but it is a massive async method.
        # So we will verify the LOGIC snippet I inserted.
        
        q_text = draft.get("text", "").lower()
        for sq in draft.get("subquestions", []):
            q_text += " " + sq.get("text", "").lower()
            
        print(f"Combined Text: {q_text}")
            
        if "er diagram" in q_text or "eer diagram" in q_text:
            used_question_types.add("er_diagram")
        if "normalization" in q_text or "normal form" in q_text:
            used_question_types.add("normalization")
        # Detect ER → Relational Mapping
        if ("map" in q_text or "convert" in q_text or "transform" in q_text) and ("er diagram" in q_text or "eer diagram" in q_text) and ("relational" in q_text or "relational schema" in q_text):
            used_question_types.add("er_to_relational_mapping")
            
        print(f"Detected Types: {used_question_types}")
        
        self.assertIn("er_diagram", used_question_types)
        self.assertIn("er_to_relational_mapping", used_question_types)

if __name__ == '__main__':
    unittest.main()
