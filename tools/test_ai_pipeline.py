#!/usr/bin/env python3
"""
Internal Developer Tool: Test AI Pipeline
Usage: python3 tools/test_ai_pipeline.py

This script sends a standard 'Ideal Bundle' to the local API to verify the AI logic.
"""

import requests
import json
import sys

API_URL = "http://localhost:8000/ai/analyze"

def get_ideal_bundle():
    """Returns the Standard Test Bundle with Code Snippets"""
    return {
        "id": "dev_test_bundle_001",
        "windowStart": "2023-10-27T14:00:10Z",
        "windowEnd": "2023-10-27T14:05:10Z",
        "rootService": "payment-service",
        "logPatterns": [
            {
                "pattern": "ConnectionTimeout: timed out after 5000ms",
                "count": 150,
                "firstOccurrence": "2023-10-27T14:00:10Z",
                "lastOccurrence": "2023-10-27T14:05:00Z",
                "errorClass": "DatabaseError"
            }
        ],
        "metrics": {
            "latencyZ": 4.5,
            "errorRateZ": 3.8
        },
        # THIS IS KEY: The Code Snippet the AI needs to see
        "code_snippets": [
            {
                "file_path": "src/config/database.py",
                "start_line": 40,
                "end_line": 45,
                "content": "def get_db_connection():\n    # Connect to primary DB\n    return connect(\n        host=ENV.DB_HOST,\n        timeout=5  # <--- AI SEES THIS\n    )"
            }
        ],
        "git_context": {
            "repo_url": "https://github.com/org/opscure-ml",
            "branch": "main",
            "commit_hash": "HEAD"
        }
    }

def main():
    print(f"🚀 Sending Ideal Bundle to {API_URL}...")
    
    try:
        response = requests.post(
            API_URL, 
            json={"bundle": get_ideal_bundle()}
        )
        response.raise_for_status()
        
        data = response.json()
        
        print("\n✅ AI Response Received:")
        print(json.dumps(data, indent=2))
        
        # Quick validation
        recs = data.get("recommendation", {}).get("recommendations", [])
        if recs:
            print(f"\n🎯 Top Recommendation: {recs[0]['title']}")
            print(f"🛠  Fix Type: {recs[0]['implementation']['type']}")
        else:
            print("\n⚠️  No recommendations found.")
            
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Could not connect to {API_URL}. Is the server running?")
        print("Run: python3 -m src.api.main` in another terminal.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
