import subprocess
import sys
import os
import time
import signal

def start():
    root = os.getcwd()
    venv_python = os.path.join(root, ".venv", "Scripts", "python.exe")
    if not os.path.exists(venv_python):
        venv_python = sys.executable  # Fallback

    print("🚀 Starting Backend...")
    # Start backend in a new console window on Windows for visibility if preferred, 
    # but here we'll just run it as a subprocess.
    backend_proc = subprocess.Popen(
        [venv_python, "start_server.py"],
        cwd=root
    )

    print("🚀 Starting Frontend...")
    frontend_dir = os.path.join(root, "frontend")
    npm_cmd = "npm.cmd" if os.name == "nt" else "npm"
    
    frontend_proc = subprocess.Popen(
        [npm_cmd, "start"],
        cwd=frontend_dir
    )

    print("\n✅ Services launched!")
    print(f"Backend: http://127.0.0.1:8000")
    print(f"Frontend: http://localhost:3000")
    print("\nKeep this terminal open. Press Ctrl+C to exit.\n")

    try:
        # Keep the script alive while processes are running
        while True:
            if backend_proc.poll() is not None:
                print("Backend service stopped.")
                break
            if frontend_proc.poll() is not None:
                print("Frontend service stopped.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Cleanup
        backend_proc.terminate()
        frontend_proc.terminate()
        print("Goodbye!")

if __name__ == "__main__":
    start()
