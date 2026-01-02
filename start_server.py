import sys
import os
import uvicorn

# Ensure 'backend' is in python path
current_dir = os.getcwd()
backend_path = os.path.join(current_dir, "backend")
if backend_path not in sys.path:
    sys.path.append(backend_path)

if __name__ == "__main__":
    print(f"🐍 Python: {sys.executable}")
    print(f"📂 Root: {current_dir}")
    print(f"📂 Backend: {backend_path}")

    # Check Motor
    try:
        import motor.motor_asyncio
        print("✅ Motor check passed.")
    except ImportError as e:
        print(f"❌ Motor check failed: {e}")
        print("Run: pip install motor")
        sys.exit(1)

    print("🚀 Starting Server (http://127.0.0.1:8000)...")
    # Using 'app.main:app' assumes 'app' is importable from 'backend' path
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
