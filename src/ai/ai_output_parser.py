"""
AI Output Parser Module
Safely parses and validates LLM output into structured AIRecommendation.
"""

import json
import re
from typing import Optional, Any
from src.common.types import AIRecommendation, create_degraded_recommendation
from src.remediation.types import RemediationProposal, RemediationPlan, RemediationAction, ActionType


class AIOutputParser:
    """
    Parses LLM output into structured AIRecommendation.
    
    Handles:
    - JSON extraction from mixed text
    - Validation of required fields
    - Default values for missing fields
    - Graceful degradation on parse errors
    """
    
    # Required fields in the AI response
    REQUIRED_FIELDS = ["root_cause_analysis", "recommendations", "confidence_assessment"]
    
    @classmethod
    def parse(
        cls,
        raw_output: str,
        bundle_id: str
    ) -> AIRecommendation:
        """
        Parse raw LLM output into AIRecommendation.
        """
        try:
            # Extract JSON from the output
            json_str = cls._extract_json(raw_output)
            
            if not json_str:
                print("[AIOutputParser] No JSON found in output")
                return create_degraded_recommendation(bundle_id)
            
            # Parse JSON
            data = json.loads(json_str)
            
            # Build AIRecommendation directly from data (pydantic handles validation)
            # We add metadata fields here
            data["correlation_bundle_id"] = bundle_id
            data["raw_model_output"] = raw_output[:5000] if raw_output else None
            
            return AIRecommendation(**data)
            
        except json.JSONDecodeError as e:
            print(f"[AIOutputParser] JSON parse error: {e}")
            return create_degraded_recommendation(bundle_id)
        except Exception as e:
            print(f"[AIOutputParser] Unexpected error: {e}")
            return create_degraded_recommendation(bundle_id)
            
    @classmethod
    def parse_remediation_proposal(cls, raw_output: str) -> Optional[RemediationProposal]:
        """
        Parse raw LLM output into RemediationProposal.
        Expects a JSON structure matching the RemediationProposal schema.
        """
        try:
            json_str = cls._extract_json(raw_output)
            if not json_str:
                return None
                
            data = json.loads(json_str)
            
            # Reconstruct objects
            # 1. Plan
            plan_data = data.get("plan", {})
            plan = RemediationPlan(
                title=plan_data.get("title", "Unknown Plan"),
                reasoning=plan_data.get("reasoning", "No reasoning provided"),
                validation_strategy=plan_data.get("validation_strategy", "Manual verification"),
                risk_assessment=plan_data.get("risk_assessment", "High")
            )
            
            # 2. Actions
            actions = []
            for act in data.get("actions", []):
                act_type = ActionType(act.get("type", "COMMAND"))
                actions.append(RemediationAction(
                    type=act_type,
                    command=act.get("command", ""),
                    arguments=act.get("arguments", []),
                    context=act.get("context", ".")
                ))
                
            # 3. Confidence (AI's self-assessment)
            confidence = float(data.get("confidence_score", 0.0))
            
            return RemediationProposal(
                plan=plan,
                actions=actions,
                confidence_score=confidence
            )
            
        except Exception as e:
            print(f"[AIOutputParser] Error parsing remediation proposal: {e}")
            return None
    
    @classmethod
    def _extract_json(cls, text: str) -> Optional[str]:
        """
        Extract JSON from text that may contain other content.
        """
        if not text:
            return None
        
        text = text.strip()
        
        # Try direct parse first
        if text.startswith("{"):
            try:
                json.loads(text)
                return text
            except json.JSONDecodeError:
                pass
        
        # Remove markdown code blocks
        code_block_pattern = r"```(?:json)?\s*\n?([\s\S]*?)\n?```"
        matches = re.findall(code_block_pattern, text, re.IGNORECASE)
        
        for match in matches:
            try:
                json.loads(match.strip())
                return match.strip()
            except json.JSONDecodeError:
                continue
        
        # Try to find JSON object in text
        json_pattern = r"\{[\s\S]*\}"
        matches = re.findall(json_pattern, text)
        
        matches.sort(key=len, reverse=True)
        
        for match in matches:
            try:
                json.loads(match)
                return match
            except json.JSONDecodeError:
                continue
        
        return None
    
    @classmethod
    def validate_recommendation(cls, rec: AIRecommendation) -> list[str]:
        """
        Validate an AIRecommendation and return any issues.
        """
        issues = []
        
        if not rec.root_cause_analysis.primary_cause or rec.root_cause_analysis.primary_cause == "unknown":
            issues.append("Root cause is unknown or missing")
        
        if not rec.recommendations:
            issues.append("No recommendations provided")
        
        if rec.confidence_assessment.final_confidence == 0.0:
            issues.append("Confidence is zero")
        
        if rec.auto_heal_candidate and rec.confidence_assessment.final_confidence < 0.7:
            issues.append("Auto-heal candidate with low confidence")
        
        return issues

