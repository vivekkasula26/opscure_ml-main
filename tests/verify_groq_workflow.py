
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Force Groq provider
os.environ["LLM_PROVIDER"] = "groq"
os.environ["GROQ_API_KEY"] = "mock-key"

from src.ai.groq_client import GroqClient
from src.ai.ai_adapter_service import AIAdapterService, get_ai_adapter_service
from src.common.types import CorrelationBundle

async def test_groq_switching():
    print("\n=== Verifying Groq Provider Switching ===\n")
    
    # 1. Verify Factory Logic
    # We need to reset the singleton first if it was already initialized
    import src.ai.ai_adapter_service
    src.ai.ai_adapter_service._ai_adapter_service = None
    
    service = await get_ai_adapter_service()
    
    # Check internal client type
    client_type = type(service._llm_client).__name__
    print(f" -> Initialized Client Type: {client_type}")
    
    if client_type == "GroqClient":
        print("SUCCESS: Factory correctly chose GroqClient.")
    else:
        print(f"FAILURE: Expected GroqClient, got {client_type}")
        return

    # 2. Verify Execution Flow (Mocked)
    print("\n=== Verifying Execution Flow ===\n")
    
    # Mock the actual network call in GroqClient
    mock_response = """{
        "root_cause_analysis": {
            "summary": "Test Summary",
            "primary_cause": "Test Cause",
            "impact": "Test Impact"
        },
        "causal_chain": [],
        "recommendations": [],
        "confidence_assessment": {
            "final_confidence": 0.9,
            "action": "auto_heal",
            "threshold_used": 0.85,
            "risk_level": "low",
            "breakdown": {},
            "adjustments": {"bonuses": [], "penalties": []},
            "reasoning": "High confidence test",
            "decision_factors": {}
        },
        "requires_human_review": false,
        "auto_heal_candidate": true
    }"""
    
    # Patch the generate method
    service._llm_client.generate = AsyncMock(return_value=mock_response)
    
    bundle = CorrelationBundle(
        id="test_groq_1",
        windowStart="2023-01-01T00:00:00Z",
        windowEnd="2023-01-01T00:05:00Z"
    )
    
    print(" -> Calling create_ai_recommendation...")
    rec = await service.create_ai_recommendation(bundle, use_rag=False)
    
    print(f" -> Received Confidence: {rec.confidence_assessment.final_confidence}")
    
    if rec.confidence_assessment.final_confidence == 0.9:
        print("SUCCESS: Groq workflow executed and parsed correctly.")
    else:
        print("FAILURE: Incorrect confidence parsed.")

if __name__ == "__main__":
    asyncio.run(test_groq_switching())
