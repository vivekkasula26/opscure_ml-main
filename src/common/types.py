"""
Core Domain Types for Opscure AI Pipeline
Types for CorrelationBundle → AIRecommendation flow
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


# =============================================================================
# CORRELATION BUNDLE (INPUT)
# =============================================================================

class LogPattern(BaseModel):
    """Detected log pattern within the correlation window"""
    pattern: str
    count: int
    firstOccurrence: str
    lastOccurrence: str
    errorClass: Optional[str] = None


class Event(BaseModel):
    """Kubernetes or system event"""
    id: str
    type: str
    reason: str
    pod: Optional[str] = None
    service: Optional[str] = None
    timestamp: str


class Metrics(BaseModel):
    """Anomaly metrics as Z-scores"""
    cpuZ: Optional[float] = None
    memZ: Optional[float] = None
    latencyZ: Optional[float] = None
    errorRateZ: Optional[float] = None
    anomalyVector: Optional[List[float]] = None


class SequenceItem(BaseModel):
    """Ordered sequence of events/logs/metrics in the correlation window"""
    timestamp: str
    type: str  # "log" | "event" | "metric"
    message: str
    sequenceIndex: int


class CorrelationBundle(BaseModel):
    """
    Complete correlation bundle representing a grouped incident.
    This is the INPUT to the AI pipeline.
    """
    id: str = Field(default_factory=lambda: f"corr_{uuid.uuid4().hex[:12]}")
    windowStart: str
    windowEnd: str
    rootService: Optional[str] = None
    affectedServices: List[str] = Field(default_factory=list)
    
    logPatterns: List[LogPattern] = Field(default_factory=list)
    events: List[Event] = Field(default_factory=list)
    metrics: Metrics = Field(default_factory=Metrics)
    
    dependencyGraph: List[str] = Field(default_factory=list)
    sequence: List[SequenceItem] = Field(default_factory=list)
    
    derivedRootCauseHint: Optional[str] = None
    
    # Git Context
    git_context: Optional["GitContext"] = None
    code_snippets: List["CodeSnippet"] = Field(default_factory=list)
    git_config: Optional["GitConfig"] = None


class GitContext(BaseModel):
    """Git repository context"""
    repo_url: str
    branch: str
    commit_hash: str
    recent_commits: List[str] = Field(default_factory=list)


class CodeSnippet(BaseModel):
    """Relevant code snippet for analysis"""
    file_path: str
    content: str
    start_line: int
    end_line: int


class GitConfig(BaseModel):
    """Git user configuration for applying fixes"""
    user_name: str
    user_email: str
    local_config_content: Optional[str] = None
    global_config_content: Optional[str] = None


# =============================================================================
# DETAILED AI OUTPUT TYPES
# =============================================================================

class RootCauseAnalysis(BaseModel):
    """Detailed root cause analysis with evidence"""
    summary: str
    primary_cause: str
    contributing_factors: List[str] = Field(default_factory=list)
    timeline: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    impact: str

class CausalChainStep(BaseModel):
    """Single step in the causal chain with metrics"""
    step: int
    event: str
    timestamp: str
    metric: Optional[str] = None
    value: Optional[float] = None
    normal: Optional[float] = None
    anomaly_score: Optional[float] = None
    max: Optional[float] = None
    wait_time_ms: Optional[float] = None
    affected_requests: Optional[int] = None

class FileEdit(BaseModel):
    """Structured file edit for robust patching"""
    file_path: str
    original_context: str
    replacement_text: str
    xml_selector: Optional[str] = None
    xml_value: Optional[str] = None

class ImplementationDetails(BaseModel):
    """Detailed implementation steps for a fix"""
    type: str  # e.g., "kubectl", "sql", "api", "git_workflow"
    commands: List[str] = Field(default_factory=list)
    file_edits: List[FileEdit] = Field(default_factory=list)
    pre_checks: List[str] = Field(default_factory=list)
    post_checks: List[str] = Field(default_factory=list)

class RollbackPlan(BaseModel):
    """Rollback strategy"""
    commands: List[str] = Field(default_factory=list)
    automatic_rollback_if: List[str] = Field(default_factory=list)
    rollback_time_seconds: int

class SimilarCase(BaseModel):
    """Reference to a similar historical case"""
    incident_id: str
    similarity: float
    fix_applied: str
    outcome: str
    resolution_time_minutes: int

class Recommendation(BaseModel):
    """Ranked recommendation with full context"""
    rank: int
    recommendation_id: str = Field(default_factory=lambda: f"rec_{uuid.uuid4().hex[:8]}")
    title: str
    description: str
    fix_type: str
    estimated_effort: str
    estimated_time_minutes: int
    risk_level: str
    cost_impact: str
    
    implementation: Optional[ImplementationDetails] = None
    current_state: Optional[Dict[str, Any]] = None
    target_state: Optional[Dict[str, Any]] = None
    rollback: Optional[RollbackPlan] = None
    
    reasoning: str
    side_effects: List[str] = Field(default_factory=list)
    ai_confidence: float
    similar_cases: List[SimilarCase] = Field(default_factory=list)

class ConfidenceAssessment(BaseModel):
    """Detailed confidence breakdown"""
    final_confidence: float
    action: str  # "auto_heal", "manual_review", etc.
    threshold_used: float
    risk_level: str
    breakdown: Dict[str, float]
    adjustments: Dict[str, List[str]]
    reasoning: str
    decision_factors: Dict[str, Any]

class AIRecommendation(BaseModel):
    """
    Enhanced AI-generated recommendation based on CorrelationBundle analysis.
    This is the OUTPUT of the AI pipeline.
    """
    incident_id: str = Field(default_factory=lambda: f"inc_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}")
    analysis_id: str = Field(default_factory=lambda: f"analysis_{uuid.uuid4().hex[:12]}")
    correlation_bundle_id: str
    analyzed_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    processing_time_ms: float = 0.0
    
    root_cause_analysis: RootCauseAnalysis
    causal_chain: List[CausalChainStep]
    recommendations: List[Recommendation]
    confidence_assessment: ConfidenceAssessment
    
    requires_human_review: bool
    auto_heal_candidate: bool
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
    raw_model_output: Optional[Any] = None  # Kept for debugging/storage


# =============================================================================
# RETRIEVED INCIDENT (FROM PINECONE)
# =============================================================================

class RetrievedIncident(BaseModel):
    """Historical incident retrieved from Pinecone for RAG context"""
    id: str
    summary: str
    rootCause: str
    recommendedAction: str
    confidence: float = Field(ge=0.0, le=1.0)


# =============================================================================
# DEGRADED RESPONSE (FALLBACK)
# =============================================================================

def create_degraded_recommendation(bundle_id: str) -> AIRecommendation:
    """Create a degraded recommendation when all AI models fail"""
    return AIRecommendation(
        correlation_bundle_id=bundle_id,
        root_cause_analysis=RootCauseAnalysis(
            summary="Analysis failed due to model unavailability",
            primary_cause="unknown",
            impact="unknown"
        ),
        causal_chain=[],
        recommendations=[],
        confidence_assessment=ConfidenceAssessment(
            final_confidence=0.0,
            action="manual_review",
            threshold_used=0.0,
            risk_level="unknown",
            breakdown={},
            adjustments={"penalties": [], "bonuses": []},
            reasoning="Model failure",
            decision_factors={}
        ),
        requires_human_review=True,
        auto_heal_candidate=False,
        metadata={"error": "All models failed"},
        raw_model_output={"error": "All models failed"}
    )
