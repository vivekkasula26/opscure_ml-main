"""
Remediation Types Module

Defines the core data structures for the Remediation Engine.
Distinguishes between the "Plan" (Human Readable) and the "Action" (Machine Executable).
"""

from typing import List, Optional, Union, Literal
from dataclasses import dataclass
from enum import Enum
from src.common.types import GitConfig

class ActionType(Enum):
    COMMAND = "COMMAND"
    PATCH = "PATCH"
    API_CALL = "API_CALL"
    FILE_EDIT = "FILE_EDIT"
    XML_EDIT = "XML_EDIT"
    RUNTIME_OP = "RUNTIME_OP"

@dataclass
class RemediationAction:
    """
    An executable unit of work.
    SAFE for machine execution (after approval).
    """
    type: ActionType
    command: str  # The shell command or API endpoint. For FILE_EDIT, this is description.
    arguments: Optional[List[str]] = None
    context: Optional[str] = None # e.g., cwd or file path
    
    # New fields for Context-Aware Patching
    file_path: Optional[str] = None
    original_context: Optional[str] = None
    replacement_text: Optional[str] = None
    xml_selector: Optional[str] = None # e.g. "dependency", "plugin"
    xml_value: Optional[str] = None    # e.g. artifactId to remove
    
    def to_string(self) -> str:
        if self.type == ActionType.COMMAND:
            args = " ".join(self.arguments) if self.arguments else ""
            return f"{self.command} {args}"
        elif self.type == ActionType.FILE_EDIT:
            return f"EDIT_FILE {self.file_path}: {self.command}"
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
    git_config: Optional[GitConfig] = None
