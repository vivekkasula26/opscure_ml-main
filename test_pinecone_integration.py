import requests
import time
import json
from src.common.types import CorrelationBundle, LogPattern, Event, Metrics, SequenceItem

BASE_URL = "http://localhost:8000"

def get_example_bundle():
    """Create a simple bundle for testing"""
    return {
        "id": "test_rag_bundle",
        "windowStart": "2024-12-05T10:00:00Z",
        "windowEnd": "2024-12-05T10:05:00Z",
        "rootService": "payment-service",
        "affectedServices": ["payment-service", "database"],
        "logPatterns": [
            {
                "pattern": "Connection refused to database",
                "count": 10,
                "firstOccurrence": "2024-12-05T10:00:00Z",
                "lastOccurrence": "2024-12-05T10:05:00Z"
            }
        ],
        "events": [],
        "metrics": {},
        "dependencyGraph": [],
        "sequence": []
    }

def test_pinecone_health():
    print("\n1. Checking Pinecone Health...")
    try:
        response = requests.get(f"{BASE_URL}/ready")
        data = response.json()
        
        pinecone_status = data.get("components", {}).get("pinecone", {})
        print(f"   Status: {json.dumps(pinecone_status, indent=2)}")
        
        if pinecone_status.get("status") == "healthy":
            print("   ✅ Pinecone is HEALTHY")
            return True
        else:
            print("   ❌ Pinecone is UNHEALTHY or Initializing")
            return False
            
    except Exception as e:
        print(f"   ❌ Error checking health: {e}")
        return False

def test_rag_analysis():
    print("\n2. Testing RAG Analysis...")
    bundle = get_example_bundle()
    
    try:
        # Request with use_rag=True (default)
        payload = {
            "bundle": bundle,
            "use_rag": True,
            "top_k": 3
        }
        
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/ai/analyze", json=payload)
        duration = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"   ✅ Analysis successful ({duration:.2f}s)")
            print(f"   Recommendation ID: {result['recommendation']['incident_id']}")
            
            # Check if we got a real response (not degraded)
            if result['recommendation']['confidence_assessment']['final_confidence'] > 0:
                 print("   ✅ Got valid confidence score")
            else:
                 print("   ⚠️  Got zero confidence (mock/degraded response)")
                 
        else:
            print(f"   ❌ Analysis failed: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"   ❌ Error during analysis: {e}")

if __name__ == "__main__":
    print("=== Testing Pinecone Integration ===")
    
    # Wait a bit for server to fully initialize Pinecone
    if test_pinecone_health():
        test_rag_analysis()
    else:
        print("\nSkipping analysis test because Pinecone is not ready.")
