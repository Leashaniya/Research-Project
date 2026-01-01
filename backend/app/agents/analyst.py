import json
from pathlib import Path
from .base import BaseAgent
from app.core.paths import ARTIFACTS_DIR

class BlueprintAnalyst(BaseAgent):
    """
    The Blueprint Analyst Agent.
    Role: Analyze past papers to determine the exam structure (blueprint).
    """

    def __init__(self, config=None):
        super().__init__(name="Blueprint Analyst", config=config)
        self.blueprint_path = ARTIFACTS_DIR / "exam_blueprint_template.json"

    async def run(self, input_data: dict = None) -> dict:
        """
        Analyses the past papers (conceptually) and returns the Exam Blueprint.
        
        In this iteration, it loads the pre-generated blueprint from the 'structure_topics_template.py' script output.
        Future V2: This agent will dynamically use an LLM to read the PDFs and infer the structure on-the-fly.
        """
        self.log("Analyzing past papers to determine structure...")
        
        # logic to load existing blueprint or run the structure script
        if not self.blueprint_path.exists():
            self.log("Blueprint not found, triggering generation script...")
            # Ideally we would call the script logic here if it wasn't already run
            # For now, we assume the linear pipeline Step 3 has run or we mock it.
            # Returning a fallback/default blueprint if missing is safer for the agent.
            return self._default_blueprint()

        try:
            blueprint = json.loads(self.blueprint_path.read_text(encoding="utf-8"))
            self.log("Blueprint loaded successfully.")
            return blueprint
        except Exception as e:
            self.log(f"Error loading blueprint: {e}")
            return self._default_blueprint()

    def _default_blueprint(self):
        """Fallback blueprint if analysis fails."""
        self.log("Using DEFAULT Blueprint fallback.")
        return {
            "exam_title": "Model Exam (Fallback)",
            "question_slots": [
                {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
                {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
                {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
                {"question_no": "Q4", "target_marks": 25, "topics": ["General"]},
            ]
        }
