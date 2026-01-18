
import asyncio
from unittest.mock import MagicMock, patch
from src.remediation.types import RemediationProposal, RemediationPlan, RemediationAction, ActionType
from src.remediation.confidence import ConfidenceScorer, ConfidenceResult
from src.remediation.safety import SafetyLevel, SafetyPolicy
from src.ai.agent import RemediationAgent

async def test_runtime_remediation():
    print("\n=== Testing Runtime Remediation Workflow ===\n")
    
    # 1. Create a "Runtime" Proposal (e.g., Restart Pod)
    # This simulates what the AI Adapter would produce for an OOM event
    proposal = RemediationProposal(
        plan=RemediationPlan(
            title="Restart Payment Service Pod",
            reasoning="Memory usage at 98%, indicative of leak or spike. Ephemeral fix.",
            validation_strategy="Check pod status after restart",
            risk_assessment="Low"
        ),
        actions=[
            RemediationAction(
                type=ActionType.RUNTIME_OP,
                command="kubectl delete pod payment-service-123"
            )
        ],
        confidence_score=0.75 # Medium confidence, usually would fail strict code checks (0.8/0.9)
    )
    
    # 2. Initialize Components
    # We need a real ConfidenceScorer to test the threshold logic
    mock_store = MagicMock()
    mock_store.get_success_rate.return_value = None # No history
    
    scorer = ConfidenceScorer(feedback_store=mock_store)
    agent = RemediationAgent()
    agent.confidence_engine = scorer # Inject real scorer
    
    # 4. Threshold Verification
    print("\n--- Testing Thresholds ---")
    
    # Case A: 0.75 (Should Fail)
    print("Testing 0.75:")
    res_low = scorer.evaluate(proposal, 0.75)
    print(f" -> Decision: {res_low.decision}")
    assert res_low.decision == SafetyLevel.REQUIRE_APPROVAL
    
    # Case B: 0.98 (Should Fail - strictly must be >= 0.99)
    print("Testing 0.98:")
    res_high = scorer.evaluate(proposal, 0.98)
    print(f" -> Decision: {res_high.decision}")
    assert res_high.decision == SafetyLevel.REQUIRE_APPROVAL
    
    # Case C: 0.99 (Should Pass)
    # Note: We need to mock history to be fully safe? 
    # Logic: if score >= 0.99 + History ...
    # Wait, code says: "if history is None... return REQUIRE_APPROVAL requesting first-time approval"
    # So even 0.99 might FAIL if no history!
    # Let's mock history success.
    mock_store.get_success_rate.return_value = 1.0
    
    print("Testing 0.99 (with History):")
    res_safe = scorer.evaluate(proposal, 0.99)
    print(f" -> Decision: {res_safe.decision}")
    assert res_safe.decision == SafetyLevel.SAFE

    print("SUCCESS: strict 99% threshold verified.")

    # 5. Agent Execution (Simulated)
    agent.confidence_engine.evaluate = MagicMock(return_value=ConfidenceResult(0.99, SafetyLevel.SAFE, "Forced Strict"))
    agent_result = agent.run(proposal)
    
    print("Execution Logs:")
    for log in agent_result.execution_logs:
        print(f" - {log}")
        if "Executing Runtime Operation" in log:
             print("SUCCESS: identified RUNTIME_OP correctly.")

if __name__ == "__main__":
    asyncio.run(test_runtime_remediation())
