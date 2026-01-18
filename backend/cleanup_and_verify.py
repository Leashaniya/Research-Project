
import os
import shutil
from pathlib import Path
import subprocess
import time

def cleanup():
    base_dir = Path("backend/data/outputs/model_papers")
    files_to_delete = [
        "generation_checkpoint.json",
        "agentic_model_paper.json",
        "agentic_model_paper.pdf"
    ]
    
    print("🧹 Cleaning up old artifacts...")
    for fname in files_to_delete:
        fpath = base_dir / fname
        if fpath.exists():
            try:
                os.remove(fpath)
                print(f"   Deleted: {fpath}")
            except Exception as e:
                print(f"   ❌ Failed to delete {fpath}: {e}")
    
    # Also clean temp_images if exists
    temp_dir = base_dir / "temp_images"
    if temp_dir.exists():
        try:
            shutil.rmtree(temp_dir)
            print(f"   Deleted directory: {temp_dir}")
        except Exception as e:
            print(f"   ❌ Failed to delete {temp_dir}: {e}")

    print("✅ Cleanup complete.")

def run_verify():
    print("🚀 Starting verification (fresh run)...")
    try:
        # Run verify_agents.py
        result = subprocess.run(["python", "backend/verify_agents.py"], check=True)
        print(f"✅ Verification finished with code {result.returncode}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    cleanup()
    # Wait a bit to ensure file system sync
    time.sleep(2)
    run_verify()
