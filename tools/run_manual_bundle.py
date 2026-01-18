
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from src.common.types import CorrelationBundle
from src.ai.ai_adapter_service import AIAdapterService
from src.ai.groq_client import GroqClient
from src.ai.ollama_client import OllamaClient
from src.remediation.confidence import ConfidenceResult
from src.remediation.safety import SafetyLevel, SafetyPolicy
from src.ai.agent import RemediationAgent

# TRANSCRIPT FROM USER IMAGE
CUSTOM_BUNDLE_DATA = {
    "id": "bundle13012026_01",
    "windowStart": "2026-01-13T06:21:02Z",
    "windowEnd": "2026-01-13T06:21:02Z",
    "rootService": "unknown",
    "affectedServices": [
        "unknown",
        "com.beko:DemoBank_v1:jar",
        "org.springframework.boot",
        "com.beko",
        "spring-boot:2.7.15",
        "resources:3.2.0",
        "compiler:3.10.1"
    ],
    "logPatterns": [
        {
            "pattern": "[INFO]",
            "count": 4,
            "firstOccurrence": "2026-01-13T06:21:02Z",
            "lastOccurrence": "2026-01-13T06:21:02Z",
            "errorClass": None
        },
        {
            "pattern": "[INFO] ----------------------< com.beko:DemoBank_v1 >----------------------\n[INFO] Building DemoBank_v1 0.0.1-SNAPSHOT\n[INFO] from pom.xml\n[INFO] --------------------------------[ jar ]---------------------------------",
            "count": 1,
            "firstOccurrence": "2026-01-13T06:21:02Z",
            "lastOccurrence": "2026-01-13T06:21:02Z",
            "errorClass": None
        },
        {
            "pattern": "[INFO] Using 'UTF-8' encoding to copy filtered resources.",
            "count": 2,
            "firstOccurrence": "2026-01-13T06:21:02Z",
            "lastOccurrence": "2026-01-13T06:21:02Z",
            "errorClass": None
        }
    ]
}

# Mock AI Response to simulate a realistic analysis of these logs
# Since these are INFO logs, a real AI might say "No Error".
# But to demonstrate the workflow, let's assume the user thinks there IS an issue or wants to see the "Healthy" state.
# OR, lets assume the logs stopped abruptly implying a crash? 
# Let's return a "Status Report" style response.
MOCK_AI_ANALYSIS = """
{
  "root_cause_analysis": {
    "primary_cause": "Normal Operation Check",
    "summary": "The logs indicate a standard Maven build initialization for DemoBank_v1. No explicit errors found in the provided snippet.",
    "impact": "None",
    "contributing_factors": [],
    "timeline": [
      "06:21:02Z - Build started for DemoBank_v1",
      "06:21:02Z - Resource copying using UTF-8"
    ],
    "evidence": {
      "log_pattern": "[INFO] Building DemoBank_v1"
    }
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Monitor Build Completion",
      "description": "Ensure the build completes successfully as no errors are present yet.",
      "fix_type": "preventive_recommendation",
      "risk_level": "Low",
      "estimated_effort": "Low",
      "estimated_time_minutes": 1,
      "cost_impact": "None",
      "implementation": {
        "type": "api",
        "commands": [],
        "pre_checks": [],
        "post_checks": []
      },
      "ai_confidence": 0.95,
      "reasoning": "Logs show successful start.",
      "side_effects": [],
      "rollback": null
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.95,
    "action": "manual_review",
    "threshold_used": 0.99,
    "risk_level": "Low",
    "breakdown": {},
    "adjustments": {},
    "reasoning": "High confidence in 'Healthy' assessment.",
    "decision_factors": {}
  },
  "causal_chain": [],
  "requires_human_review": false,
  "auto_heal_candidate": false
}
"""

async def run_pipeline():
    print(f"\n🚀 Processing Bundle: {CUSTOM_BUNDLE_DATA['id']}")
    print("==================================================")
    
    # 1. Hydrate Bundle
    from src.common.git_utils import GitConfigCollector
    
    # Collect real git config
    git_config = GitConfigCollector.collect_config(".")
    
    bundle = CorrelationBundle(**CUSTOM_BUNDLE_DATA)
    if git_config:
        bundle.git_config = git_config
        print(f"✅ Loaded Git Config: {git_config.user_name} <{git_config.user_email}>")
        if git_config.local_config_content:
             print("   - Found Local .git/config")
        if git_config.global_config_content:
             print("   - Found Global ~/.gitconfig")
    
    # 2. Setup Service with Mocked LLM (to guarantee output for this demo)
    # in a real run, this would call Ollama/Groq
    mock_client = MagicMock()
    mock_client.generate_with_fallback = AsyncMock(return_value=(MOCK_AI_ANALYSIS, "llama3-mock"))
    
    service = AIAdapterService(llm_client=mock_client)
    
    # 3. Generate Proposal (The "Think" Phase)
    print("\n🧠 AI Understanding Logs...")
    proposal = await service.create_remediation_proposal(bundle)
    
    if not proposal:
        print("❌ AI failed to generate proposal.")
        return

    print("\n✅ AI Analysis Complete")
    # Debug: Check if config files are in the prompt (by inspecting the prompt construction)
    # Since we can't easily intercept the internal prompt variable without mocking more, 
    # we rely on the fact that no error occurred and the types flow through.
    # But let's print the config object we passed to be sure.
    print(f"   [Debug] Bundle GitConfig: {bundle.git_config.user_name} (Global Content Len: {len(bundle.git_config.global_config_content or '')})")

    print(f"   Root Cause: {proposal.plan.title} (Reason: {proposal.plan.reasoning})")
    print(f"   Confidence Score: {proposal.confidence_score}")
    print(f"   Proposed Action: {proposal.actions[0].type if proposal.actions else 'None'}")
    
    # 4. Run Agent (The "Act" Phase)
    print("\n🤖 Agent Evaluating Safety...")
    agent = RemediationAgent()
    
    # We expect this to REQUIRE_APPROVAL (0.95 < 0.99)
    result = agent.run(proposal)
    
    print("\n🏁 Final Output")
    print("================")
    print(f"Decision: {result.confidence_result.decision.name}")
    print(f"Reason: {result.confidence_result.reason}")
    print("Execution Logs:")
    for log in result.execution_logs:
        print(f"  - {log}")

if __name__ == "__main__":
    asyncio.run(run_pipeline())
