"""
Test script to verify backend and frontend connectivity
"""
import requests
import time
import sys
import os

# Fix Windows console encoding
if sys.platform == 'win32':
    os.system('chcp 65001 >nul 2>&1')

def test_backend():
    """Test if backend is running and responding"""
    print("[TEST] Testing backend connection...")
    
    max_retries = 5
    for i in range(max_retries):
        try:
            response = requests.get('http://localhost:8000/files', timeout=2)
            if response.status_code == 200:
                data = response.json()
                print("[OK] Backend is running!")
                print(f"    Status: {response.status_code}")
                print(f"    Past Papers: {len(data.get('past_papers', []))} files")
                print(f"    Lecture Slides: {len(data.get('lecture_slides', []))} files")
                if data.get('past_papers'):
                    print(f"    Sample papers: {data['past_papers'][:3]}")
                if data.get('lecture_slides'):
                    print(f"    Sample slides: {data['lecture_slides'][:3]}")
                return True
        except requests.exceptions.ConnectionError:
            if i < max_retries - 1:
                print(f"    [WAIT] Waiting for backend to start... (attempt {i+1}/{max_retries})")
                time.sleep(2)
            else:
                print("[ERROR] Backend is not running!")
                print("    Please start it with: python start_server.py")
                return False
        except Exception as e:
            print(f"[ERROR] Error connecting to backend: {e}")
            return False
    
    return False

def test_cors():
    """Test CORS headers"""
    print("\n[TEST] Testing CORS configuration...")
    try:
        response = requests.options(
            'http://localhost:8000/files',
            headers={
                'Origin': 'http://localhost:3000',
                'Access-Control-Request-Method': 'GET'
            },
            timeout=2
        )
        cors_headers = {
            'access-control-allow-origin': response.headers.get('access-control-allow-origin'),
            'access-control-allow-methods': response.headers.get('access-control-allow-methods'),
            'access-control-allow-headers': response.headers.get('access-control-allow-headers'),
        }
        print(f"[OK] CORS Headers: {cors_headers}")
        return True
    except Exception as e:
        print(f"[WARN] Could not test CORS: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Backend Connection")
    print("=" * 60)
    
    backend_ok = test_backend()
    
    if backend_ok:
        test_cors()
        print("\n" + "=" * 60)
        print("[SUCCESS] Backend is ready!")
        print("    Frontend should be able to connect at http://localhost:3000")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("[FAILED] Backend is not running")
        print("    Start it with: python start_server.py")
        print("=" * 60)
        sys.exit(1)
