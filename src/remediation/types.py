"""
Remediation Types Module

Defines the core data structures for the Remediation Engine.
Distinguishes between the "Plan" (Human Readable) and the "Action" (Machine Executable).
"""

from typing import List, Optional, Union, Literal
from dataclasses import dataclass
from enum import Enum

class ActionType(Enum):
    COMMAND = "COMMAND"
    PATCH = "PATCH"
    API_CALL = "API_CALL"

@dataclass
class RemediationAction:
    """
    An executable unit of work.
    SAFE for machine execution (after approval).
    """
    type: ActionType
    command: str  # The shell command or API endpoint
    arguments: Optional[List[str]] = None
    context: Optional[str] = None # e.g., cwd or file path
    
    def to_string(self) -> str:
        if self.type == ActionType.COMMAND:
            args = " ".join(self.arguments) if self.arguments else ""
            return f"{self.command} {args}"
        return self.command

@dataclass
class RemediationPlan:
    """
    A human-readable explanation of the strategy.
    Designed for User Review.
    """
    title: str
    reasoning: str
    validation_strategy: str
    risk_assessment: str # Low, Medium, High

@dataclass
class RemediationProposal:
    """
    The full proposal container.
    """
    plan: RemediationPlan
    actions: List[RemediationAction]
    confidence_score: float # 0.0 to 1.0 (from Confidence Engine)
