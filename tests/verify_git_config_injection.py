
import asyncio
from typing import List
from src.ai.agent import RemediationAgent
from src.remediation.types import RemediationProposal, RemediationPlan, RemediationAction, ActionType
from src.common.types import GitConfig
from src.remediation.safety import SafetyLevel

# Mock Confidence Result to force SAFE execution
from collections import namedtuple
MockConfidenceResult = namedtuple('MockConfidenceResult', ['decision', 'final_score'])

def test_git_config_injection():
    print("=== Testing Git Config Injection in RemediationAgent ===")
    
    # 1. Setup Data
    git_config = GitConfig(user_name="Test Bot", user_email="bot@test.com")
    
    actions = [
        RemediationAction(type=ActionType.COMMAND, command="git commit -m 'fix: bug'", context="."),
        RemediationAction(type=ActionType.COMMAND, command="ls -la", context=".") # Should NOT be injected
    ]
    
    plan = RemediationPlan(
        title="Test Git Config",
        reasoning="Testing config injection",
        validation_strategy="None",
        risk_assessment="Low"
    )
    
    proposal = RemediationProposal(
        plan=plan,
        actions=actions,
        confidence_score=0.99,
        git_config=git_config
    )
    
    # 2. Setup Agent
    agent = RemediationAgent()
    
    # Mocking confidence engine to always return SAFE
    agent.confidence_engine.evaluate = lambda p, s: MockConfidenceResult(decision=SafetyLevel.SAFE, final_score=0.99)
    
    # 3. Run
    result = agent.run(proposal)
    
    # 4. Verify Logs
    print("\n[Execution Logs]")
    for log in result.execution_logs:
        print(log)
        
    # Check for injection
    injected_cmd = "git -c user.name='Test Bot' -c user.email='bot@test.com' commit -m 'fix: bug'"
    
    found_git = False
    found_ls = False
    
    for log in result.execution_logs:
        if f"Executing: {injected_cmd}" in log:
            found_git = True
        if "Executing: ls -la" in log:
            found_ls = True
            
    if found_git:
        print("\n✅ SUCCESS: Git command was correctly injected with config.")
    else:
        print(f"\n❌ FAILURE: Git command was NOT injected correctly.\nExpected: {injected_cmd}")
        
    if found_ls:
        print("✅ SUCCESS: Non-git command was left untouched.")
    else:
        print("❌ FAILURE: Non-git command was modified or not executed.")

if __name__ == "__main__":
    test_git_config_injection()
