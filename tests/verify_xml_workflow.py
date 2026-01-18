
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock

from src.common.types import CorrelationBundle, AIRecommendation
from src.ai.prompt_builder import PromptBuilder
from src.ai.ai_adapter_service import AIAdapterService
from src.remediation.types import ActionType

# Mock AI Response for XML Edit
MOCK_XML_RESPONSE = """
{
  "root_cause_analysis": {
    "primary_cause": "Bad dependency",
    "summary": "Dependence on log4j 1.x",
    "impact": "Security",
    "contributing_factors": [],
    "timeline": [],
    "evidence": {}
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Remove Log4j",
      "description": "Remove vulnerable dependency.",
      "fix_type": "xml_block_edit",
      "estimated_effort": "Low",
      "estimated_time_minutes": 5,
      "risk_level": "Low",
      "cost_impact": "None",
      "implementation": {
        "type": "file_edit",
        "commands": [],
        "file_edits": [
            {
                "file_path": "/app/pom.xml",
                "original_context": "",
                "replacement_text": "",
                "xml_selector": "dependency",
                "xml_value": "log4j"
            }
        ],
        "pre_checks": [],
        "post_checks": []
      },
      "ai_confidence": 0.99,
      "reasoning": "Standard removal.",
      "side_effects": [],
      "rollback": null
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.99,
    "action": "auto_heal",
    "threshold_used": 0.99,
    "risk_level": "Low",
    "breakdown": {},
    "adjustments": {},
    "reasoning": "High confidence",
    "decision_factors": {}
  },
  "causal_chain": [],
  "requires_human_review": false,
  "auto_heal_candidate": true
}
"""

async def verify_xml_workflow():
    print("=== Verifying XML Workflow Integration ===")
    
    # 1. Verify Prompt Builder
    print("\n[1] Checking Prompt Builder...")
    # Just check if system prompt contains instructions
    assert "FOR XML/POM FIXES" in PromptBuilder.SYSTEM_PROMPT
    assert "xml_block_edit" in PromptBuilder.SYSTEM_PROMPT
    assert "xml_selector" in PromptBuilder.OUTPUT_SCHEMA
    print("SUCCESS: Prompt instructions present.")
    
    # 2. Verify Adapter Mapping
    print("\n[2] Checking Adapter Mapping...")
    
    # Mock LLM
    mock_client = MagicMock()
    mock_client.generate_with_fallback = AsyncMock(return_value=(MOCK_XML_RESPONSE, "mock-model"))
    
    service = AIAdapterService(llm_client=mock_client)
    
    # Create dummy bundle
    bundle = CorrelationBundle(id="test_xml_1", windowStart="2023-01-01T00:00:00Z", windowEnd="2023-01-01T00:05:00Z")
    
    # Generate Proposal
    proposal = await service.create_remediation_proposal(bundle)
    
    if not proposal:
        print("FAILURE: No proposal generated.")
        return
        
    # Check Action Type
    action = proposal.actions[0]
    print(f"Generated Action Type: {action.type}")
    print(f"XML Selector: {action.xml_selector}")
    print(f"XML Value: {action.xml_value}")
    
    assert action.type == ActionType.XML_EDIT
    assert action.xml_selector == "dependency"
    assert action.xml_value == "log4j"
    print("SUCCESS: Adapter correctly mapped to XML_EDIT.")

if __name__ == "__main__":
    asyncio.run(verify_xml_workflow())
