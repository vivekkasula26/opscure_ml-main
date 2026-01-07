import requests
import json
import uuid
from datetime import datetime

BASE_URL = "http://localhost:8000"

def create_git_bundle():
    """
    Construct a CorrelationBundle with Git context.
    """
    bundle = {
        "id": f"corr_git_{uuid.uuid4().hex[:8]}",
        "windowStart": "2024-12-05T10:00:00Z",
        "windowEnd": "2024-12-05T10:45:00Z",
        "rootService": "order-service",
        "affectedServices": ["order-service"],
        "logPatterns": [
            {
                "pattern": "java.lang.OutOfMemoryError: Java heap space",
                "count": 15,
                "firstOccurrence": "2024-12-05T10:15:00Z",
                "lastOccurrence": "2024-12-05T10:45:00Z",
                "errorClass": "OutOfMemoryError"
            }
        ],
        "events": [],
        "metrics": {
            "memZ": 4.5
        },
        "dependencyGraph": ["order-service"],
        "sequence": [],
        
        # NEW: Git Context
        "git_context": {
            "repo_url": "https://github.com/opscure/order-service",
            "branch": "main",
            "commit_hash": "a1b2c3d4e5f6",
            "recent_commits": [
                "a1b2c3d - feat: add local caching for orders",
                "b2c3d4e - fix: update dependencies",
                "c3d4e5f - chore: readme update"
            ]
        },
        
        # NEW: Code Snippets
        "code_snippets": [
            {
                "file_path": "src/main/java/com/example/orders/OrderProcessor.java",
                "start_line": 45,
                "end_line": 55,
                "content": """
    public class OrderProcessor {
        // Local cache for faster lookup
        private Map<String, Order> cache = new HashMap<>();

        public void process(Order order) {
            cache.put(order.getId(), order);
            // ... processing logic
        }
    }
                """
            }
        ],
        
        # NEW: Git Config
        "git_config": {
            "user_name": "Opscure Bot",
            "user_email": "bot@opscure.io"
        }
    }
    
    return bundle

def run_test():
    print("=== Testing Git Context Integration ===")
    
    bundle = create_git_bundle()
    print(f"Created Bundle ID: {bundle['id']}")
    print(f"Git Context: {bundle['git_context']['repo_url']} @ {bundle['git_context']['branch']}")
    print(f"Code Snippets: {len(bundle['code_snippets'])}")
    
    try:
        print("\nSending to /ai/analyze...")
        response = requests.post(f"{BASE_URL}/ai/analyze", json={
            "bundle": bundle,
            "use_rag": False # Disable RAG to focus on Git context
        })
        
        if response.status_code == 200:
            result = response.json()
            rec = result["recommendation"]
            
            print("\n✅ Analysis Complete!")
            print("-" * 50)
            print(f"Root Cause: {rec['root_cause_analysis']['summary']}")
            print(f"Confidence: {rec['confidence_assessment']['final_confidence']}")
            
            # Check for code fix
            for r in rec['recommendations']:
                if r['fix_type'] == 'code':
                    print(f"\nFound Code Fix: {r['title']}")
                    print(f"Implementation Type: {r['implementation']['type']}")
                    print(f"Commands: {json.dumps(r['implementation']['commands'], indent=2)}")
            
            print("-" * 50)
            
        else:
            print(f"\n❌ Error: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"\n❌ Exception: {e}")

if __name__ == "__main__":
    run_test()
