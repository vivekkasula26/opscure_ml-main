"""
Remediation Engine Verification Demo

Tests three scenarios:
1. SAFE: High confidence + Safe action -> Auto Execute.
2. APPROVAL: High confidence + Dangerous action -> Request Approval.
3. BLOCKED: Any confidence + Blocked action -> Blocked.
"""

import sys
import os
from unittest.mock import patch
from dataclasses import dataclass

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock missing dependencies
from unittest.mock import MagicMock
sys.modules["aiohttp"] = MagicMock()

from src.ai.agent import MockLLM
from src.ai.ai_adapter_service import AIAdapterService
from src.common.types import CorrelationBundle, LogPattern, Metrics
import asyncio

# Mock Bundle
mock_bundle = CorrelationBundle(
    windowStart="1000",
    windowEnd="2000",
    logPatterns=[LogPattern(pattern="Disk full", count=100, firstOccurrence="1000", lastOccurrence="2000")],
    metrics=Metrics(cpuZ=2.5),
    events=[],
    dependencyGraph=[],
    rootService="backend",
    affectedServices=["backend"]
)

async def run_test(name, mock_json):
    print(f"\n--- Running Test: {name} ---")
    
    # Patch the MockLLM to return our specific test case
    with patch.object(MockLLM, 'generate', return_value=mock_json):
        # Use AIAdapterService
        service = AIAdapterService()
        
        # We need to manually inject or point to the feedback store if we want to isolate tests,
        # but for this demo, the default internal agent creation is fine.
        
        proposal = await service.create_remediation_proposal(mock_bundle)
        
        if proposal:
            print(f"Proposal Title: {proposal.plan.title}")
            print(f"Confidence: {proposal.confidence_score}")
            print(f"Actions: {[a.to_string() for a in proposal.actions]}")
        else:
            print("No proposal generated.")

# Scenario 1: SAFE
safe_json = """
{
    "plan": {"title": "Check Logs", "reasoning": "Standard check", "validation_strategy": "None", "risk_assessment": "Low"},
    "actions": [{"type": "COMMAND", "command": "grep", "arguments": ["error", "/var/log/syslog"]}],
    "confidence_score": 0.95
}
"""

# Scenario 2: APPROVAL REQUIRED (Policy says rm is allowed but dangerous)
approval_json = """
{
    "plan": {"title": "Delete Pod", "reasoning": "Stuck pod", "validation_strategy": "Check status", "risk_assessment": "Medium"},
    "actions": [{"type": "COMMAND", "command": "kubectl", "arguments": ["delete", "pod", "backend-123"]}],
    "confidence_score": 0.95
}
"""

# Scenario 3: BLOCKED
blocked_json = """
{
    "plan": {"title": "Nuke It", "reasoning": "YOLO", "validation_strategy": "None", "risk_assessment": "High"},
    "actions": [{"type": "COMMAND", "command": "rm -rf /", "arguments": []}],
    "confidence_score": 0.99
}
"""

        
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    loop.run_until_complete(run_test("SAFE SCENARIO", safe_json))
    loop.run_until_complete(run_test("APPROVAL SCENARIO", approval_json))
    loop.run_until_complete(run_test("BLOCKED SCENARIO", blocked_json))
    
    loop.close()
