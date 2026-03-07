"""Run MCQ Study Plan FastAPI server (replaces Flask run)."""
import os
import sys

# Ensure service root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Create folders
for folder in ["uploads", "outputs", "Lecture_slides", "Questions"]:
    os.makedirs(folder, exist_ok=True)

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8002"))
    print("=" * 60)
    print("  MCQ STUDY PLAN - FastAPI")
    print("=" * 60)
    print(f"  http://127.0.0.1:{port}")
    print(f"  Docs: http://127.0.0.1:{port}/docs")
    print("=" * 60)
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
