
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock
from src.common.types import CorrelationBundle, CodeSnippet
from src.ai.ai_adapter_service import AIAdapterService
from src.ai.ollama_client import OllamaClient
from src.remediation.types import ActionType

# Mock AI Response (Same as before)
IDEAL_AI_RESPONSE = """
{
  "root_cause_analysis": {
    "primary_cause": "Hardcoded timeout",
    "summary": "Timeout set to 5s",
    "impact": "High",
    "contributing_factors": [],
    "timeline": [],
    "evidence": {}
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Increase DB Timeout",
      "description": "Increase database timeout to handle load spikes.",
      "fix_type": "Code Change",
      "risk_level": "Medium",
      "implementation": {
        "type": "git_workflow",
        "commands": [
          "git checkout -b fix/timeout",
          "sed -i 's/timeout=5/timeout=30/' src/config/database.py"
        ],
        "pre_checks": [],
        "post_checks": []
      },
      "ai_confidence": 0.98,
      "reasoning": "Standard fix",
      "estimated_effort": "Low",
      "estimated_time_minutes": 5,
      "cost_impact": "None",
      "side_effects": [],
      "similar_cases": [],
      "rollback": null
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.98,
    "action": "manual_review",
    "threshold_used": 0.9,
    "risk_level": "Medium",
    "breakdown": {},
    "adjustments": {},
    "reasoning": "High confidence",
    "decision_factors": {}
  },
  "causal_chain": [],
  "requires_human_review": true,
  "auto_heal_candidate": false
}
"""

async def test_refactored_flow():
    print("\n=== Testing Refactored Agent Workflow ===\n")

    # 1. Setup Data
    bundle = CorrelationBundle(
        id="test_refactor_1",
        windowStart="2023-01-01T00:00:00Z",
        windowEnd="2023-01-01T00:05:00Z"
    )

    # 2. Mock Dependencies
    mock_ollama = MagicMock(spec=OllamaClient)
    mock_ollama.generate_with_fallback = AsyncMock(return_value=(IDEAL_AI_RESPONSE, "mock-model"))
    
    # 3. Init Service
    service = AIAdapterService(ollama_client=mock_ollama)
    
    # 4. Run the Full Flow
    # This calls create_remediation_proposal -> create_ai_recommendation -> agent.run
    print("STEP 1: Calling create_remediation_proposal...")
    proposal = await service.create_remediation_proposal(bundle)
    
    # 5. Verify Results
    if proposal:
        print("\nSUCCESS: Proposal generated!")
        print(f"Title: {proposal.plan.title}")
        print(f"Confidence: {proposal.confidence_score}")
        print(f"Actions ({len(proposal.actions)}):")
        for act in proposal.actions:
            print(f" - [{act.type.value}] {act.command}")
            
        # Verify mapping logic
        # Implementation type 'git_workflow' should map to ActionType.PATCH or COMMAND depending on logic
        # In my manual map logic I set it to PATCH if git_workflow
        print(f"Action Type Verification: {proposal.actions[0].type}")
        
    else:
        print("\nFAILURE: No proposal returned.")

if __name__ == "__main__":
    asyncio.run(test_refactored_flow())
