


import os
import sys
import subprocess
import webbrowser
import time
from threading import Timer

def open_browser():

    time.sleep(10)
    webbrowser.open('http://localhost:5000')

def check_dependencies():

    try:
        import flask
        import pandas
        import numpy
        import spacy

        
        # Check for spaCy model
        try:
            import en_core_web_sm
            print("✓ spaCy model found")
        except:

            subprocess.check_call([sys.executable, "-m", "spacy", "download", "en_core_web_sm"])
            
    except ImportError as e:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def main():
    print("=" * 60)
    print("  LECTURE QUESTION ANALYSIS SYSTEM")
    print("=" * 60)
    print()
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        sys.exit(1)

    # Check dependencies
    check_dependencies()
    
    # Create necessary folders
    folders = ['uploads', 'outputs', 'Lecture_slides', 'Questions']
    for folder in folders:
        os.makedirs(folder, exist_ok=True)
        print(f" Folder '{folder}' ready")
    
    print("\n" + "=" * 60)
    print("  Starting Flask server...")
    print("=" * 60)
    print("\n Dashboard will open automatically")
    print(" Press Ctrl+C to stop the server")
    print()
    
    # Open browser automatically
    Timer(1, open_browser).start()
    
    # Run the Flask app
    from app import app
    app.run(debug=True, host='0.0.0.0', port=5000)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n Server stopped. Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)