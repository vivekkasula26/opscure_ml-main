"""
Confidence Engine Module

The "Brain" of the Remediation System.
Decides whether an action should be auto-executed or require human approval.
Integrates AI confidence with historical feedback.
"""

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional
from src.remediation.types import RemediationProposal, RemediationAction
from src.remediation.safety import SafetyLevel, SafetyPolicy

@dataclass
class ConfidenceResult:
    final_score: float
    decision: SafetyLevel
    reason: str

class FeedbackStore:
    """
    Simple persistent store for action success rates.
    """
    def __init__(self, storage_path: str = "feedback_db.json"):
        self.storage_path = storage_path
        self._cache: Dict[str, Dict] = {}
        self._load()
    
    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r') as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {}
        else:
            self._cache = {}

    def _save(self):
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self._cache, f)
        except Exception:
            pass # Non-critical failure
            
    def record_feedback(self, action_signature: str, success: bool):
        entry = self._cache.get(action_signature, {"success": 0, "total": 0})
        entry["total"] += 1
        if success:
            entry["success"] += 1
        self._cache[action_signature] = entry
        self._save()
        
    def get_success_rate(self, action_signature: str) -> Optional[float]:
        entry = self._cache.get(action_signature)
        if not entry or entry["total"] < 3: # Need minimal sample size
            return None
        return entry["success"] / entry["total"]

class ConfidenceScorer:
    """
    Calculates the final confidence score and makes the Go/No-Go decision.
    """
    
    
    # Thresholds
    # Thresholds
    HIGH_CONFIDENCE_THRESHOLD = 0.99
    LOW_CONFIDENCE_THRESHOLD = 0.80
    
    def __init__(self, feedback_store: FeedbackStore):
        self.feedback_store = feedback_store
        
    def evaluate(self, proposal: RemediationProposal, raw_ai_confidence: float) -> ConfidenceResult:
        """
        Layer 2: The Confidence Engine (Soft Guardrails)
        If Layer 1 says "Action is Legal", Layer 2 checks Trust.
        """
        
        # 1. Safety Matrix / Policy Check (Layer 1) happens outside or we assume passed/checked before?
        # Ideally, Agent calls SafetyPolicy.evaluate_matrix first. 
        # But here we double check or assume caller passes context?
        # The prompt implies ConfidenceEngine checks "Trust".
        
        # Let's assess the raw confidence and history first.
        
        signature = proposal.plan.title
        history_score = self.feedback_store.get_success_rate(signature)
        
        # Combined score logic
        if history_score is not None:
            # If we have history, it's a strong signal.
            final_score = (raw_ai_confidence * 0.4) + (history_score * 0.6)
            reason = f"Combined AI ({raw_ai_confidence:.2f}) + History ({history_score:.2f})"
        else:
            final_score = raw_ai_confidence
            reason = f"AI Confidence ({raw_ai_confidence:.2f})"

        # Determine Threshold based on Action Type
        # Runtime ops are generally reversible, so we can be a bit more lenient.
        # Check if plan contains runtime ops
        # Check if plan contains runtime ops
        
        # Better check:
        from src.remediation.types import ActionType
        has_runtime_op = any(a.type == ActionType.RUNTIME_OP for a in proposal.actions)
        
        current_threshold = self.LOW_CONFIDENCE_THRESHOLD
        if has_runtime_op:
            # Lower threshold for runtime ops (e.g. 0.70)
            current_threshold = 0.70
            
        # Rule: Low Confidence 
        # Condition: New issue, no history, or past failures.
        # Result: Downgrade to HITL (Manual Review).
        if final_score < current_threshold:
             return ConfidenceResult(final_score, SafetyLevel.REQUIRE_APPROVAL, f"Low confidence (< {current_threshold}). Forcing HITL.")
             
        # Rule: High Confidence (> 0.9)
        # Condition: Similar past incidents verified by humans?
        # We use history_score as proxy for "verified by humans" (assuming feedback loop implies verification)
        if final_score >= self.HIGH_CONFIDENCE_THRESHOLD:
            if history_score is None:
                # High AI confidence but NO history. 
                # Is it safe to auto-heal? The prompt says: "Condition: Similar past incidents verified by humans".
                # If no history, we might want to be cautious.
                return ConfidenceResult(final_score, SafetyLevel.REQUIRE_APPROVAL, "High AI confidence but no historical verification. Requesting first-time approval.")
            else:
                 # High confidence + History exists.
                 # Check if the "Matrix" allowed it (this logic is separated, but assuming we are here, we check Trust)
                 return ConfidenceResult(final_score, SafetyLevel.SAFE, "High confidence + Verified history.")

        # Middle ground (0.8 - 0.9)
        # Probably safest to ask for approval
        return ConfidenceResult(final_score, SafetyLevel.REQUIRE_APPROVAL, "Confidence in medium range (0.8-0.9). Requesting approval.")
