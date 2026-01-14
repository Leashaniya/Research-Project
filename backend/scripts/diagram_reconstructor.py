"""
Diagram Reconstructor (VLM-Powered)
-----------------------------------
Workflow:
1. Load diagram from diagrams_manifest.json
2. VLM (Azure GPT-4o) -> Extract structured meaning (JSON)
3. Similarity Controller -> Mutate JSON for uniqueness
4. Diagram Generator -> Convert JSON to Mermaid
"""

import json
import os
import base64
import random
import sys
from pathlib import Path

# Add project root and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.core.config import settings
from backend.app.core.llm_factory import get_llm_client

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
MANIFEST_PATH = DATA_ROOT / "text_extraction_hybrid" / "diagrams_manifest.json"
OUT_ROOT = DATA_ROOT / "diagram_reconstruction"
OUT_ROOT.mkdir(parents=True, exist_ok=True)

class DiagramUnderstandingAgent:
    def __init__(self):
        self.client = get_llm_client()
        self.model = settings.AZURE_DEPLOYMENT_NAME if settings.LLM_PROVIDER == "azure" else (settings.OPENAI_MODEL or "gpt-4o")

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def analyze_image(self, image_path):
        """Use VLM to extract structured meaning from the diagram."""
        base64_image = self.encode_image(image_path)
        
        prompt = """
        Analyze this diagram image.
        1. Classify the type: (ER Diagram, Relational Schema, SQL Table, Transaction Schedule, Index Tree, Architecture Block Diagram).
        2. Extract all structural elements into JSON.
           - For ERD: entities, attributes, relationships, cardinalities.
           - For Trees: nodes, children, values.
           - For Tables: columns, rows, headers.
        
        Output JSON format:
        {
          "type": "ER Diagram",
          "elements": [
            {"id": "e1", "label": "Student", "type": "entity"},
            {"id": "r1", "label": "Enrolls", "type": "relationship"},
            {"id": "e2", "label": "Course", "type": "entity"}
          ],
          "connections": [
            {"source": "e1", "target": "r1", "cardinality": "M"},
            {"source": "r1", "target": "e2", "cardinality": "N"}
          ]
        }
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ],
                    }
                ],
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"❌ VLM Analysis failed for {image_path}: {e}")
            return None

class SimilarityController:
    """Modifies the extracted diagram meaning to create a 'similar but new' version."""
    
    def mutate(self, diagram_json):
        if not diagram_json: return None
        
        new_json = json.loads(json.dumps(diagram_json)) # Deep copy
        
        # 1. Rename Entities/Labels (Simple Obfuscation)
        # In a real system, this would use an LLM or a synonym dictionary.
        # Here we just append a suffix or genericize to prove the point.
        suffixes = ["_v2", "_New", "_System"]
        
        for el in new_json.get("elements", []):
            if "label" in el:
                el["label"] += random.choice(suffixes)
                
        # 2. Modify Cardinality (Simulation)
        for conn in new_json.get("connections", []):
            if "cardinality" in conn:
                # Flip 1:N to N:1 occasionally
                if conn["cardinality"] == "1" and random.random() > 0.8:
                    conn["cardinality"] = "M"
                    
        return new_json

class DiagramGenerator:
    """Converts structured JSON to Code (Mermaid)."""
    
    def json_to_mermaid(self, data):
        if not data: return ""
        
        dtype = data.get("type", "").lower()
        lines = []
        
        if "er" in dtype:
            lines.append("erDiagram")
            # Register entities
            for el in data.get("elements", []):
                if el.get("type") in ["entity", "weak entity"]:
                    label = el.get("label", "Entity").replace(" ", "_")
                    lines.append(f"    {label} {{ string id }}")
            
            # Register connections
            for conn in data.get("connections", []):
                src = conn.get("source_label") or conn.get("source")
                tgt = conn.get("target_label") or conn.get("target")
                card = conn.get("cardinality", "1").upper()
                
                # Resolve IDs to Labels if needed (simplified)
                # Assuming connections use IDs, we need to lookup labels. 
                # For this prototype, let's assume VLM outputs labels directly in connections or we map them.
                # Let's map IDs to Labels first
                id_map = {e["id"]: e["label"].replace(" ", "_") for e in data.get("elements", [])}
                src_lab = id_map.get(src, src)
                tgt_lab = id_map.get(tgt, tgt)
                
                rel_card = "||--o{" if card in ["M", "N"] else "||--||"
                lines.append(f"    {src_lab} {rel_card} {tgt_lab} : relates")
                
        else:
            # Default to Flowchart
            lines.append("graph TD")
            for el in data.get("elements", []):
                lbl = el.get("label", "?")
                lines.append(f"    {el['id']}['{lbl}']")
            for conn in data.get("connections", []):
                lines.append(f"    {conn['source']} --> {conn['target']}")
                
        return "\n".join(lines)

class DiagramReconstructor:
    def __init__(self):
        self.agent = DiagramUnderstandingAgent()
        self.controller = SimilarityController()
        self.generator = DiagramGenerator()

    def process_all(self):
        if not MANIFEST_PATH.exists():
            print("Manifest not found.")
            return

        manifest = json.loads(MANIFEST_PATH.read_text())
        reconstructed = []

        for item in manifest[:5]: # Process top 5 for demo
            img_path = item["diagram_file"]
            if not os.path.exists(img_path):
                continue
            
            print(f"Processing {img_path} with VLM...")
            
            # step 1: Understand
            meaning = self.agent.analyze_image(img_path)
            if not meaning:
                print(f"⚠️ Analysis failed for {img_path}, using fallback.")
                meaning = {
                    "type": "Error",
                    "elements": [{"id": "error", "label": "Diagram Analysis Failed", "type": "entity"}],
                    "connections": []
                }
            
            # step 2: Mutate
            mutated_meaning = self.controller.mutate(meaning)
            
            # step 3: Generate Code
            mermaid_code = self.generator.json_to_mermaid(mutated_meaning)
            
            # Determine pattern label
            topic = "GENERAL_THEORY"
            dt = meaning.get("type", "").lower()
            if "er" in dt: topic = "ER_EER_MODELING"
            elif "transaction" in dt: topic = "TRANSACTIONS_CONCURRENCY"
            elif "schema" in dt or "relational" in dt: topic = "SQL_DDL_DML"
            elif "tree" in dt or "index" in dt: topic = "INDEXING_STORAGE"

            reconstructed.append({
                "pdf_stem": item["pdf_stem"],
                "page_no": item["page_no"],
                "mermaid": mermaid_code,
                "pattern_label": topic,
                "raw_boxes_count": len(meaning.get("elements", []))
            })

        out_path = OUT_ROOT / "reconstructed_diagrams.json"
        out_path.write_text(json.dumps(reconstructed, indent=2))
        print(f"✅ Reconstructed diagrams saved to {out_path}")

if __name__ == "__main__":
    reconstructor = DiagramReconstructor()
    reconstructor.process_all()
