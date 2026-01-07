"""
Safety Matrix & Confidence Verification

Tests Layer 1 (Matrix) and Layer 2 (Confidence) rules.
"""

import sys
import os
from unittest.mock import MagicMock
from dataclasses import dataclass

# Mock sys.modules for aiohttp
sys.modules["aiohttp"] = MagicMock()

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.remediation.context import SafetyContext, Environment, Scope, ExecutionMode
from src.remediation.safety import SafetyPolicy, SafetyLevel
from src.remediation.confidence import ConfidenceScorer, FeedbackStore
from src.remediation.types import RemediationProposal, RemediationPlan, RemediationAction, ActionType

# --- Helper to create proposals ---
def create_proposal(title="Test Fix", confidence=0.95, cmd="ls"):
    plan = RemediationPlan(title=title, reasoning="Fix it", validation_strategy="Verify", risk_assessment="Low")
    action = RemediationAction(type=ActionType.COMMAND, command=cmd)
    return RemediationProposal(plan=plan, actions=[action], confidence_score=confidence)

# --- Mock Feedback Store ---
mock_store = MagicMock(spec=FeedbackStore)
# By default, no history
mock_store.get_success_rate.return_value = None 

# --- TESTS ---

def test_layer1_matrix():
    print("\n--- Layer 1: Safety Matrix Tests ---")
    
    # 1. Source Code + Direct Apply -> FORBIDDEN
    ctx = SafetyContext(Environment.DEV, Scope.SOURCE_CODE, ExecutionMode.DIRECT_APPLY)
    assert SafetyPolicy.evaluate_matrix(ctx) == SafetyLevel.BLOCKED
    print("PASS: Source Code + Direct Apply => BLOCKED")
    
    # 2. Source Code + AutoPR -> HITL
    ctx = SafetyContext(Environment.DEV, Scope.SOURCE_CODE, ExecutionMode.AUTO_PR)
    assert SafetyPolicy.evaluate_matrix(ctx) == SafetyLevel.REQUIRE_APPROVAL
    print("PASS: Source Code + AutoPR => HITL")
    
    # 3. Prod Infra + Direct Apply -> HITL
    ctx = SafetyContext(Environment.PROD, Scope.INFRA, ExecutionMode.DIRECT_APPLY)
    assert SafetyPolicy.evaluate_matrix(ctx) == SafetyLevel.REQUIRE_APPROVAL
    print("PASS: Prod Infra + Direct Apply => HITL")
    
    # 4. Dev Infra + Direct Apply -> SAFE
    ctx = SafetyContext(Environment.DEV, Scope.INFRA, ExecutionMode.DIRECT_APPLY)
    assert SafetyPolicy.evaluate_matrix(ctx) == SafetyLevel.SAFE
    print("PASS: Dev Infra + Direct Apply => SAFE")

def test_layer2_confidence():
    print("\n--- Layer 2: Confidence Engine Tests ---")
    scorer = ConfidenceScorer(mock_store)
    
    # 1. Low Confidence (< 0.8) -> HITL
    # Even if Layer 1 says SAFE (Dev Infra)
    prop = create_proposal(confidence=0.60)
    result = scorer.evaluate(prop, 0.60)
    assert result.decision == SafetyLevel.REQUIRE_APPROVAL
    assert "Low confidence" in result.reason
    print("PASS: Low Confidence (0.6) => HITL")
    
    # 2. High Confidence (0.95) but NO History -> HITL (First time check)
    mock_store.get_success_rate.return_value = None
    prop = create_proposal(confidence=0.95)
    result = scorer.evaluate(prop, 0.95)
    assert result.decision == SafetyLevel.REQUIRE_APPROVAL
    assert "no historical verification" in result.reason
    print("PASS: High Confidence + No History => HITL")
    
    # 3. High Confidence + Good History -> SAFE
    mock_store.get_success_rate.return_value = 1.0 # 100% success rate
    prop = create_proposal(confidence=0.95)
    result = scorer.evaluate(prop, 0.95)
    # The logic mixes scores: 0.95 * 0.4 + 1.0 * 0.6 = 0.38 + 0.6 = 0.98
    # 0.98 > 0.90 Threshold -> SAFE
    assert result.decision == SafetyLevel.SAFE
    print("PASS: High Confidence + Good History => SAFE")

if __name__ == "__main__":
    try:
        test_layer1_matrix()
        test_layer2_confidence()
        print("\nALL TESTS PASSED!")
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()
