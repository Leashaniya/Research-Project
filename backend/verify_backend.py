from fastapi.testclient import TestClient
from app.main import app
import os

client = TestClient(app)

def test_endpoints():
    print("Testing /files endpoint...")
    response = client.get("/files")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    assert response.status_code == 200
    
    print("\nTesting /model-paper/generate-paper endpoint (expecting Mock if no keys)...")
    response = client.post("/model-paper/generate-paper")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response Status Key: {data.get('status')}")
    print(f"Message: {data.get('message')}")
    
    # We expect either success or partial_success (mock)
    assert response.status_code == 200
    assert data.get('status') in ["success", "partial_success"]

    if data.get('status') == "partial_success":
        print("Verified: Fallback Mock mechanism is ACTIVE.")
    else:
        print("Verified: Real pipeline is ACTIVE.")

if __name__ == "__main__":
    try:
        test_endpoints()
        print("\n✅ All checks passed!")
    except Exception as e:
        print(f"\n❌ Tests failed: {e}")
