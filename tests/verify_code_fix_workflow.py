
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock, patch
from src.common.types import CorrelationBundle, CodeSnippet, Metrics, LogPattern, Event
from src.ai.ai_adapter_service import AIAdapterService
from src.ai.ollama_client import OllamaClient
from src.remediation.types import ActionType, RemediationProposal, RemediationPlan, RemediationAction
from src.ai.agent import RemediationAgent

# 1. Define the "Ideal" AI Response (The Mock)
IDEAL_AI_RESPONSE = """
{
  "root_cause_analysis": {
    "summary": "Application is timing out because the database connection timeout is hardcoded to 5 seconds.",
    "primary_cause": "Insufficient Hardcoded Timeout Configuration",
    "contributing_factors": ["Traffic spike", "Timeout explicitly set to 5s"],
    "timeline": [],
    "evidence": {},
    "impact": "High"
  },
  "causal_chain": [],
  "recommendations": [
    {
      "rank": 1,
      "title": "Increase DB Timeout",
      "description": "Bump the database timeout from 5s to 30s.",
      "fix_type": "Code Change",
      "estimated_effort": "Low",
      "estimated_time_minutes": 2,
      "risk_level": "Medium",
      "cost_impact": "None",
      "implementation": {
        "type": "git_workflow",
        "commands": [],
        "file_edits": [
            {
                "file_path": "src/config/database.py",
                "original_context": "def get_conn():\\n    return connect(timeout=5)",
                "replacement_text": "def get_conn():\\n    return connect(timeout=30)"
            }
        ],
        "pre_checks": ["grep 'timeout=5' src/config/database.py"],
        "post_checks": ["grep 'timeout=30' src/config/database.py"]
      },
      "rollback": { "commands": [], "automatic_rollback_if": [], "rollback_time_seconds": 0 },
      "reasoning": "Matches observed latency.",
      "side_effects": [],
      "ai_confidence": 0.98,
      "similar_cases": []
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.98,
    "action": "manual_review",
    "threshold_used": 0.9,
    "risk_level": "Medium",
    "breakdown": {},
    "adjustments": {"bonuses": [], "penalties": []},
    "reasoning": "High confidence match.",
    "decision_factors": {}
  },
  "requires_human_review": true,
  "auto_heal_candidate": false
}
"""

async def test_code_fix_workflow():
    print("\n=== Starting Code Fix Workflow Verification ===\n")

    # 2. Setup Mock Input (Correlation Bundle with Code Snippet)
    bundle = CorrelationBundle(
        id="test_bundle_123",
        windowStart="2023-10-27T10:00:00Z",
        windowEnd="2023-10-27T10:05:00Z",
        code_snippets=[
            CodeSnippet(
                file_path="src/config/database.py",
                content="def get_conn():\n    return connect(timeout=5)",
                start_line=10,
                end_line=12
            )
        ]
    )
    print(f"STEP 1: Created Mock Bundle with Code Snippet: {bundle.code_snippets[0].file_path}")

    # 3. Setup Mock AI Client
    mock_ollama = MagicMock(spec=OllamaClient)
    # Mock generate_with_fallback to return our IDEAL_AI_RESPONSE
    mock_ollama.generate_with_fallback = AsyncMock(return_value=(IDEAL_AI_RESPONSE, "llama3"))
    mock_ollama.health_check = AsyncMock(return_value={"status": "healthy"})

    # 4. Initialize Adapter
    service = AIAdapterService(llm_client=mock_ollama)
    
    # Check that we can create a remediation proposal
    # NOTE: The RemediationAgent in `ai_adapter_service.py` currently uses `MockLLM` internally 
    # for the `create_remediation_proposal` flow (lines 64-70 of agent.py).
    # To verify OUR prompt/response logic, we should test `create_ai_recommendation` 
    # which uses the injected `ollama_client`.
    
    print("STEP 2: Calling create_ai_recommendation (The 'Think' Phase)...")
    recommendation = await service.create_ai_recommendation(bundle, use_rag=False)
    
    # 5. Verify Output
    print(f"\nSTEP 3: Verify AI Output Parsing")
    first_rec = recommendation.recommendations[0]
    print(f" -> Title: {first_rec.title}")
    print(f" -> Fix Type: {first_rec.fix_type}")
    print(f" -> Implementation Type: {first_rec.implementation.type}")
    print(f" -> File Edits: {first_rec.implementation.file_edits}")
    
    assert len(first_rec.implementation.file_edits) > 0
    assert first_rec.implementation.file_edits[0].file_path == "src/config/database.py"
    print("SUCCESS: Recommendation parsed correctly with FILE_EDIT.")
    
    # 6. Verify Context Usage
    # We can check that the prompt sent to the LLM actually contained our snippet.
    # The `generate_with_fallback` was called with (prompt, system_prompt)
    call_args = mock_ollama.generate_with_fallback.call_args
    sent_prompt = call_args[1]['prompt'] # prompt is keyword arg
    
    print(f"\nSTEP 4: Verify Prompt Content")
    if "src/config/database.py" in sent_prompt and "timeout=5" in sent_prompt:
        print("SUCCESS: Prompt contained the target file and code content.")
    else:
        print(f"FAILURE: Prompt missing context.\nPrompt preview: {sent_prompt[:200]}...")
        
    print("\n=== Verification Complete (Part 1: Analysis) ===")

    # 7. Verify Agent Execution & Learning
    print("\nSTEP 5: Verify Agent Execution & Learning Loop")
    
    # Manually construct proposal from recommendation for testing
    # In real flow, AIAdapterService.create_remediation_proposal does this
    rec = recommendation.recommendations[0]
    
    # Map actions manually for test (simulating Adapter logic)
    actions = []
    if rec.implementation.file_edits:
        for edit in rec.implementation.file_edits:
            actions.append(RemediationAction(
                type=ActionType.FILE_EDIT,
                command=f"Edit {edit.file_path}",
                file_path=edit.file_path,
                original_context=edit.original_context,
                replacement_text=edit.replacement_text
            ))
            
    proposal = RemediationProposal(
        plan=RemediationPlan(
            title=rec.title,
            reasoning=rec.reasoning,
            validation_strategy="Post-execution health check",
            risk_assessment=rec.risk_level
        ),
        actions=actions,
        confidence_score=rec.ai_confidence
    )
    
    # Initialize Agent
    agent = RemediationAgent()
    
    # Mock CodePatcher.apply_patch to avoid actual filesystem writes during test
    with patch('src.remediation.patcher.CodePatcher.apply_patch') as mock_patch:
        # Mock successful patch
        from src.remediation.patcher import PatchResult
        mock_patch.return_value = PatchResult(True, "Mock Success")
        
        # Force SAFE decision
        from src.remediation.confidence import ConfidenceResult
        from src.remediation.safety import SafetyLevel
        agent.confidence_engine.evaluate = MagicMock(return_value=ConfidenceResult(
            decision=SafetyLevel.SAFE,
            final_score=0.99,
            reason="Forced Safe for Test"
        ))

        # Run Agent
        result = agent.run(proposal)
        
        print(f" -> Agent Decision: {result.confidence_result.decision}")
        
        # Verify Patch was called
        mock_patch.assert_called_once()
        print("SUCCESS: CodePatcher.apply_patch was called.")
    
    # Emulate "Success" to trigger learning
    # Even if blocked, let's force executed=True to test the save_learning method
    result.executed = True 
    
    print(" -> Calling result.save_learning()...")
    # Mock Pinecone to avoid API hits/errors
    mock_pinecone = AsyncMock()
    with patch('src.ai.agent.get_pinecone_client', AsyncMock(return_value=mock_pinecone)):
        await result.save_learning()
        
    print("SUCCESS: save_learning() called without error.")
    
    print("\n=== Verification Complete (Full Loop) ===")

if __name__ == "__main__":
    asyncio.run(test_code_fix_workflow())
