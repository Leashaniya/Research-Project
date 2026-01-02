import uvicorn
import os
import sys

# Script is in backend/scripts
# We want to add 'backend' to sys.path so we can import 'app'
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../backend/scripts
backend_dir = os.path.dirname(current_dir) # .../backend/

# Check if 'backend' is already in path
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

if __name__ == "__main__":
    print(f"🚀 Starting Server from {backend_dir}...")
    print(f"🐍 Python Executable: {sys.executable}")
    
    # Debug Import
    try:
        import motor.motor_asyncio
        print("✅ Motor library found.")
    except ImportError as e:
        print(f"❌ Motor library NOT found: {e}")
        print("Run: pip install motor")
        sys.exit(1)

    # "app.main:app" works because we added .../backend/ to sys.path
    # Disable reload for now to avoid subprocess environment issues on Windows
    try:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
    except KeyboardInterrupt:
        print("🛑 Server stopped.")
