import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from src.common.types import CorrelationBundle, GitConfig
from src.common.git_utils import GitConfigCollector
from src.ai.ai_adapter_service import AIAdapterService
from src.ai.agent import RemediationAgent
from src.remediation.confidence import ConfidenceResult
from src.remediation.safety import SafetyLevel

# 1. The User Provided Data
USER_PAYLOAD = {
 "bundle": {
   "id": "bundle15012026_01",
   "windowStart": "2026-01-15T07:21:58Z",
   "windowEnd": "2026-01-15T12:51:58Z",
   "rootService": "spring-boot:2.7.15",
   "affectedServices": [
     "spring-boot:2.7.15",
     "com.beko:DemoBank_v1:jar", # Added context
     "org.springframework.boot"
   ],
   "logPatterns": [
     {
       "pattern": "[WARNING] 'build.plugins.plugin.(groupId:artifactId)' must be unique but found duplicate declaration of plugin org.springframework.boot:spring-boot-maven-plugin @ line 128, column 12",
       "count": 1,
       "firstOccurrence": "2026-01-15T07:21:58Z",
       "lastOccurrence": "2026-01-15T07:21:58Z",
       "errorClass": "Warning"
     }
   ],
   "events": [],
   "metrics": {
     "cpuZ": 1.14,
     "latencyZ": 5.7,
     "errorRateZ": 2
   },
   "dependencyGraph": [],
   "derivedRootCauseHint": "Derived from runtime log patterns",
   "sequence": [
     {
       "timestamp": "2026-01-15T07:21:58Z",
       "type": "log",
       "message": "[WARNING] 'build.plugins.plugin.(groupId:artifactId)' must be unique but found duplicate declaration of plugin org.springframework.boot:spring-boot-maven-plugin @ line 128, column 12",
       "sequenceIndex": 1
     }
   ]
 },
 "use_rag": True,
 "top_k": 5
}

# 2. A "Realistic" AI Response tailored to these specific logs
# The AI should spot the duplicate plugin warning.
REALISTIC_AI_RESPONSE = """
{
  "root_cause_analysis": {
    "primary_cause": "Malformed Maven Build Configuration",
    "summary": "The build is issuing valid warnings about a duplicate plugin declaration in pom.xml. Specifically, 'org.springframework.boot:spring-boot-maven-plugin' is declared twice.",
    "impact": "Build stability risk. Future Maven versions may fail.",
    "contributing_factors": ["Duplicate <plugin> tag in pom.xml"],
    "timeline": [],
    "evidence": {
      "log": "found duplicate declaration of plugin org.springframework.boot:spring-boot-maven-plugin"
    }
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Remove Duplicate Maven Plugin",
      "description": "Remove the redundant declaration of spring-boot-maven-plugin from pom.xml to fix the build warning.",
      "fix_type": "xml_block_edit",
      "risk_level": "Low",
      "estimated_effort": "Low",
      "estimated_time_minutes": 2,
      "cost_impact": "None",
      "implementation": {
        "type": "file_edit",
        "commands": [],
        "file_edits": [
          {
            "file_path": "/Users/supreeth/spring-app/pom.xml", 
            "original_context": "<plugin>...spring-boot-maven-plugin...</plugin>",
            "replacement_text": "",
            "xml_selector": "plugin",
            "xml_value": "spring-boot-maven-plugin"
          }
        ],
        "pre_checks": ["mvn validate"],
        "post_checks": ["mvn validate"]
      },
      "ai_confidence": 0.98,
      "reasoning": "Explicit warning in logs identifying exact location of duplicate.",
      "side_effects": [],
      "rollback": null
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.98,
    "action": "auto_heal",
    "threshold_used": 0.90,
    "risk_level": "Low",
    "breakdown": {},
    "adjustments": {},
    "reasoning": "High confidence due to explicit error message.",
    "decision_factors": {}
  },
  "causal_chain": [],
  "requires_human_review": false,
  "auto_heal_candidate": true
}
"""

async def run_scenario():
    print(f"\n🚀 Processing User Bundle: {USER_PAYLOAD['bundle']['id']}")
    print("==================================================")
    
    # 1. Hydrate Bundle
    # Note: We are mocking the file path in the 'implementation' above because we don't know the user's real file structure 
    # from the JSON alone, but the AI would usually deduce it from 'git_context' or file paths in logs.
    
    bundle_data = USER_PAYLOAD['bundle']
    # Filter out extra fields if needed or let Pydantic ignore extras (default behavior)
    bundle = CorrelationBundle(**bundle_data)
    
    # Collect real git config
    git_config = GitConfigCollector.collect_config(".")
    if git_config:
        bundle.git_config = git_config
        print(f"✅ Loaded Git Config: {git_config.user_name} <{git_config.user_email}>")

    # 2. Setup Real Service
    # Ensure environment variables are loaded for API keys if using Groq
    from dotenv import load_dotenv
    from src.ai import get_ai_adapter_service
    load_dotenv()
    
    print("\n🔌 Connecting to Real AI Service...")
    try:
        service = await get_ai_adapter_service()
    except Exception as e:
        print(f"❌ Failed to initialize AI service: {e}")
        return
    
    # 3. Generate Proposal
    print("\n🧠 AI Understanding Logs...")
    proposal = await service.create_remediation_proposal(bundle)
    
    if not proposal:
        print("❌ AI failed to generate proposal.")
        return

    print("\n✅ AI Analysis Complete")
    print(f"   Root Cause: {proposal.plan.title}")
    print(f"   Reasoning:  {proposal.plan.reasoning}")
    print(f"   Confidence: {proposal.confidence_score}")
    
    # 4. Run Agent
    print("\n🤖 Agent Evaluating Safety...")
    agent = RemediationAgent()
    result = agent.run(proposal)
    
    print("\n🏁 Final Output")
    print("================")
    print(f"Decision: {result.confidence_result.decision.name}")
    if result.executed:
        print("Status: EXECUTED")
    else:
        print(f"Status: BLOCKED / PENDING ({result.confidence_result.reason})")
        
    print("Execution Logs:")
    for log in result.execution_logs:
        print(f"  - {log}")

if __name__ == "__main__":
    asyncio.run(run_scenario())
