
import os
import asyncio
from src.ai.groq_client import GroqClient
from src.ai.ai_adapter_service import get_ai_adapter_service
from src.common.types import CorrelationBundle

# Ensure we are using Groq
os.environ["LLM_PROVIDER"] = "groq"

async def verify_real_groq():
    print("=== Testing Real Groq API Connection ===")
    
    # 1. Check if Key is present
    key = os.getenv("GROQ_API_KEY")
    if not key:
        print("ERROR: GROQ_API_KEY not found in environment.")
        return

    # 2. Initialize Service
    service = await get_ai_adapter_service()
    print(f" -> Service Initialized with: {type(service._llm_client).__name__}")

    # 3. Create Simple Bundle
    bundle = CorrelationBundle(
        id="live_test_1",
        windowStart="2023-01-01T00:00:00Z",
        windowEnd="2023-01-01T00:05:00Z",
        logPatterns=[
            {"pattern": "Connection refused to database:5432", "count": 50, "firstOccurrence": "2023-01-01T00:00:00Z", "lastOccurrence": "2023-01-01T00:05:00Z"}
        ]
    )

    # 4. Call Real API
    print(" -> Sending request to Groq (Llama 3 70B)...")
    try:
        # We use use_rag=False to avoid needing a valid Pinecone setup for this specific test
        recommendation = await service.create_ai_recommendation(bundle, use_rag=False)
        print("\n=== Real AI Response ===")
        print(f"Root Cause: {recommendation.root_cause_analysis.primary_cause}")
        print(f"Confidence: {recommendation.confidence_assessment.final_confidence}")
        
        if recommendation.confidence_assessment.final_confidence > 0:
            print("\nSUCCESS: Received valid response from Groq!")
        else:
            print("\WARNING: Response parsed but confidence is 0.")
            
    except Exception as e:
        print(f"\nFAILURE: API Call failed: {e}")

if __name__ == "__main__":
    asyncio.run(verify_real_groq())
