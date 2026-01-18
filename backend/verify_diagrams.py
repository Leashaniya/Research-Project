
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from backend.app.services.diagram_service import DiagramService

def test_diagram_generation():
    print("Testing DiagramService (Kroki.io)...")
    
    # 1. ER Diagram Example
    er_code = """
    erDiagram
        CUSTOMER ||--o{ ORDER : places
        ORDER ||--|{ LINE-ITEM : contains
        CUSTOMER }|..|{ DELIVERY-ADDRESS : uses
    """
    
    out_path = Path("backend/data/outputs/test_diagram_er.png")
    
    success = DiagramService.render_mermaid_to_image(er_code, str(out_path.absolute()))
    
    if success and out_path.exists():
        print(f"✅ Success! Image created at {out_path}")
    else:
        print("❌ Failed to generate image.")
        exit(1)

if __name__ == "__main__":
    test_diagram_generation()
