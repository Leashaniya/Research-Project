import sys
import os
import uvicorn

# Ensure service root is in Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

if __name__ == "__main__":
    print(f"🐍 Python: {sys.executable}")
    print(f"📂 Root: {current_dir}")

    # Check Motor
    try:
        import motor.motor_asyncio
        print("✅ Motor check passed.")
    except ImportError as e:
        print(f"❌ Motor check failed: {e}")
        print("Run: pip install motor")
        sys.exit(1)

    port = int(os.environ.get("PORT", 8000))
    print(f"🚀 Starting Server (http://127.0.0.1:{port})...")
    # Using 'app.main:app' assumes 'app' is importable from service root
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=False)
