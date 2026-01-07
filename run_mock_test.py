import requests
import json
import time

def run_mock_test():
    print("1. Fetching example bundle...")
    try:
        response = requests.get("http://localhost:8000/ai/example-bundle")
        response.raise_for_status()
        bundle = response.json()
        print("   Success! Got bundle with ID:", bundle.get("id"))
    except Exception as e:
        print(f"   Failed to get bundle: {e}")
        return

    print("\n2. Sending bundle to /ai/analyze/no-rag (Mock Mode)...")
    try:
        start_time = time.time()
        # Using no-rag to avoid external dependencies and ensure a result
        response = requests.post("http://localhost:8000/ai/analyze/no-rag", json=bundle)
        response.raise_for_status()
        result = response.json()
        duration = time.time() - start_time
        
        print(f"   Success! Analysis took {duration:.2f}s")
        print("\n=== REAL OUTPUT ===")
        print(json.dumps(result, indent=2))
        print("===================")
        
    except Exception as e:
        print(f"   Failed to analyze bundle: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Server response: {e.response.text}")

if __name__ == "__main__":
    run_mock_test()
