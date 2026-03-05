"""Start MCQ Study Plan FastAPI server."""
import os
import sys

# Ensure service root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

PORT = int(os.getenv("PORT", "8002"))

if __name__ == "__main__":
    import uvicorn
    print(f"MCQ Study Plan API: http://127.0.0.1:{PORT}")
    print(f"Docs: http://127.0.0.1:{PORT}/docs")
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=False)
