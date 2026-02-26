"""
Developer-Facing API Response Contract
=======================================
IncidentResponse is the clean output contract from the Opscure AI pipeline.
It is designed to be consumed directly by the fix component — self-contained,
flat, and unambiguous.

Status flow:
    fix_available      → fixes[] has actionable file_edits/commands
    pending_approval   → fix_available but requires human sign-off
    no_actionable_fix  → diagnosed root cause, but no automatable fix
    manual_review      → AI confidence too low to surface fixes
    analysis_failed    → LLM/parse failure, degraded response
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


# =============================================================================
# NESTED TYPES
# =============================================================================

class FileEdit(BaseModel):
    """A single find-and-replace edit on a file."""
    file: str               # Relative path from repo root
    find: str               # Exact text to find (context lines included)
    replace: str            # Replacement text


class FixItem(BaseModel):
    """
    A fully self-contained fix the fix component can apply.
    The fix component needs nothing else beyond this object.
    """
    fix_id: str = Field(default_factory=lambda: f"fix_{uuid.uuid4().hex[:6]}")
    rank: int                           # 1 = highest priority

    title: str
    description: str
    risk: str                           # "low" | "medium" | "high"
    effort: str                         # "low" | "medium" | "high"

    file_edits: List[FileEdit] = Field(default_factory=list)
    commands: List[str] = Field(default_factory=list)   # Shell commands (no file edit needed)

    verify: List[str] = Field(default_factory=list)     # Run after apply — check exit code
    rollback: Optional[str] = None                      # Single command to undo the fix


class DiagnosisSummary(BaseModel):
    """Human-readable diagnosis. Informs the approval decision."""
    summary: str                                        # One paragraph explanation
    root_cause: str                                     # One-line root cause
    severity: str                                       # "critical" | "high" | "medium" | "low"
    affected_services: List[str] = Field(default_factory=list)
    affected_files: List[str] = Field(default_factory=list)  # From git_context.changed_files
    causal_chain: List[str] = Field(default_factory=list)    # Ordered failure sequence


class IncidentMeta(BaseModel):
    """Audit trail — not used by fix component."""
    # model_used: Optional[str] = None
    rag_incidents_used: int = 0
    similar_cases: List[str] = Field(default_factory=list)  # similar case IDs from RAG


# =============================================================================
# TOP-LEVEL CONTRACT
# =============================================================================

class IncidentResponse(BaseModel):
    """
    Developer-facing action contract.

    The fix component reads this top-to-bottom:
      1. Check `status`
      2. Read `diagnosis` for context / approval decision
      3. Iterate `fixes[]` — apply file_edits, run commands, run verify
      4. On verify failure → run rollback
    """
    model_config = {"populate_by_name": True}

    # Identity
    incident_id: str
    analyzed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    processing_time_ms: Optional[float] = None

    # Fix component reads this first
    status: str  # "fix_available" | "pending_approval" | "no_actionable_fix" | "manual_review" | "analysis_failed"

    diagnosis: DiagnosisSummary
    fixes: List[FixItem] = Field(default_factory=list)

    # Control flags for fix component
    confidence: float
    approval_required: bool
    auto_applied: bool = False          # Set to True by fix component after execution

    # Audit — preserved but not consumed by fix component (underscore prefix = internal)
    meta: IncidentMeta = Field(default_factory=IncidentMeta, alias="_meta", serialization_alias="_meta")
