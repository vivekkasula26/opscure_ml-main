import requests
import json
import uuid
from datetime import datetime

BASE_URL = "http://localhost:8000"

def create_bundle_from_logs():
    """
    Construct a CorrelationBundle from the user-provided logs.
    """
    # 1. Define the logs (using the JSON format provided)
    logs = [
      {
        "timestamp": "2024-12-04T10:30:15.123Z",
        "level": "ERROR",
        "service": "auth-service",
        "pod": "auth-service-7d8f9b6c4-xkj9m",
        "message": "NullPointerException: Cannot invoke 'User.getProfile()' because 'user' is null",
        "errorClass": "NullPointerException"
      },
      {
        "timestamp": "2024-12-04T10:30:17.456Z",
        "level": "ERROR",
        "service": "api-gateway",
        "pod": "api-gateway-5c7d8f9b-plm2n",
        "message": "Authentication service timeout after 5000ms",
        "errorClass": "TimeoutError"
      },
      {
        "timestamp": "2024-12-04T10:30:20.789Z",
        "level": "ERROR",
        "service": "frontend",
        "pod": "frontend-web-6f8c9d7-qrs3p",
        "message": "User authentication failed: Gateway timeout",
        "errorClass": "AuthenticationError"
      },
      {
        "timestamp": "2024-12-04T10:31:05.234Z",
        "level": "ERROR",
        "service": "payment-service",
        "pod": "payment-service-8e9f0a1-tuv4q",
        "message": "Database connection pool exhausted",
        "errorClass": "ConnectionPoolExhaustedException"
      },
      {
        "timestamp": "2024-12-04T10:32:15.567Z",
        "level": "ERROR",
        "service": "order-service",
        "pod": "order-service-9f0a1b2-wxy5r",
        "message": "Out of memory error",
        "errorClass": "OutOfMemoryError"
      }
    ]

    # 2. Map to LogPatterns (aggregating for simplicity)
    log_patterns = []
    for log in logs:
        log_patterns.append({
            "pattern": log["message"],
            "count": 1,
            "firstOccurrence": log["timestamp"],
            "lastOccurrence": log["timestamp"],
            "errorClass": log.get("errorClass")
        })

    # 3. Map to SequenceItems
    sequence = []
    for i, log in enumerate(logs):
        sequence.append({
            "timestamp": log["timestamp"],
            "type": "log",
            "message": f"[{log['service']}] {log['message']}",
            "sequenceIndex": i
        })

    # 4. Construct the Bundle
    bundle = {
        "id": f"corr_custom_{uuid.uuid4().hex[:8]}",
        "windowStart": "2024-12-04T10:30:00Z",
        "windowEnd": "2024-12-04T10:35:00Z",
        "rootService": "auth-service", # Hinting based on first error
        "affectedServices": ["auth-service", "api-gateway", "frontend", "payment-service", "order-service"],
        "logPatterns": log_patterns,
        "events": [], # No k8s events provided in snippet
        "metrics": {
            "errorRateZ": 5.0, # Inferring high error rate
            "latencyZ": 3.5    # Inferring high latency due to timeouts
        },
        "dependencyGraph": ["frontend", "api-gateway", "auth-service", "payment-service", "order-service"],
        "sequence": sequence,
        "derivedRootCauseHint": "Cascading failure starting from auth-service"
    }
    
    return bundle

def run_analysis():
    print("=== Analyzing Custom Logs ===")
    
    bundle = create_bundle_from_logs()
    print(f"Created Bundle ID: {bundle['id']}")
    print(f"Contains {len(bundle['logPatterns'])} log patterns from 5 services.")
    
    try:
        # Send to API
        print("\nSending to /ai/analyze...")
        response = requests.post(f"{BASE_URL}/ai/analyze", json={
            "bundle": bundle,
            "use_rag": True # Try to use Pinecone if available
        })
        
        if response.status_code == 200:
            result = response.json()
            rec = result["recommendation"]
            
            print("\n✅ Analysis Complete!")
            print("-" * 50)
            print(f"Root Cause: {rec['root_cause_analysis']['summary']}")
            print(f"Confidence: {rec['confidence_assessment']['final_confidence']}")
            print("-" * 50)
            
            print("\nFull Recommendation:")
            print(json.dumps(rec, indent=2))
            
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    run_analysis()
