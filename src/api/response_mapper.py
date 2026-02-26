"""
Response Mapper
===============
Maps internal AIRecommendation → developer-facing IncidentResponse.

This is the ONLY place that knows about both types.
The fix component only ever sees IncidentResponse.
"""

from typing import Optional, List
from src.common.types import AIRecommendation, CorrelationBundle
from src.api.response_types import (
    IncidentResponse,
    DiagnosisSummary,
    FixItem,
    FileEdit,
    IncidentMeta,
)


# Confidence threshold below which approval is always required
_AUTO_APPLY_THRESHOLD = 0.85

# Risk levels that always require approval regardless of confidence
_HIGH_RISK_LEVELS = {"high", "critical", "unknown"}

# Severity mapping from risk_level strings the AI may produce
_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "moderate": "medium",
    "low": "low",
    "unknown": "high",   # Unknown → treat as high to be safe
}


class ResponseMapper:
    """
    Stateless mapper: AIRecommendation + CorrelationBundle → IncidentResponse.
    """

    @classmethod
    def map(
        cls,
        recommendation: AIRecommendation,
        bundle: CorrelationBundle,
    ) -> IncidentResponse:
        """
        Map AIRecommendation to IncidentResponse.

        Args:
            recommendation: Internal AI analysis result
            bundle:         Original CorrelationBundle (for git context + service info)
        """
        confidence = recommendation.confidence_assessment.final_confidence

        # ── Build fixes ────────────────────────────────────────────────────
        fixes = cls._build_fixes(recommendation)

        # ── Determine status ───────────────────────────────────────────────
        status = cls._determine_status(recommendation, fixes, confidence)

        # ── Determine approval_required ────────────────────────────────────
        approval_required = cls._needs_approval(recommendation, fixes, confidence)

        # ── Build diagnosis ────────────────────────────────────────────────
        diagnosis = cls._build_diagnosis(recommendation, bundle)

        # ── Build meta (audit trail) ───────────────────────────────────────
        meta = cls._build_meta(recommendation)

        return IncidentResponse(
            incident_id=recommendation.correlation_bundle_id,
            analyzed_at=recommendation.analyzed_at,
            processing_time_ms=round(recommendation.processing_time_ms, 1) if recommendation.processing_time_ms else None,
            status=status,
            diagnosis=diagnosis,
            fixes=fixes,
            confidence=round(confidence, 3),
            approval_required=approval_required,
            auto_applied=False,
            meta=meta,
        )

    # ── Private helpers ────────────────────────────────────────────────────

    @classmethod
    def _build_fixes(cls, rec: AIRecommendation) -> List[FixItem]:
        """Convert recommendations into FixItems.

        Previously this dropped recommendations with no file_edits AND no commands,
        which caused 'fixes: []' when the AI identified a fix but lacked code context.
        Now every recommendation becomes a FixItem — commands/file_edits are just empty.
        """
        fixes = []

        for r in rec.recommendations:
            impl = r.implementation

            file_edits = []
            commands: List[str] = []
            verify: List[str] = []

            if impl:
                file_edits = [
                    FileEdit(
                        file=fe.file_path,
                        find=fe.original_context,
                        replace=fe.replacement_text,
                    )
                    for fe in (impl.file_edits or [])
                ]
                commands = impl.commands or []
                verify = impl.post_checks or []

            # Rollback: use first rollback command if available
            rollback_cmd = None
            if r.rollback and r.rollback.commands:
                rollback_cmd = r.rollback.commands[0]

            fixes.append(FixItem(
                fix_id=f"fix_{str(r.rank).zfill(3)}",
                rank=r.rank,
                title=r.title,
                description=r.description,
                risk=r.risk_level.lower() if r.risk_level else "unknown",
                effort=r.estimated_effort.lower() if r.estimated_effort else "unknown",
                file_edits=file_edits,
                commands=commands,
                verify=verify,
                rollback=rollback_cmd,
            ))

        return fixes


    @classmethod
    def _determine_status(
        cls,
        rec: AIRecommendation,
        fixes: List[FixItem],
        confidence: float,
    ) -> str:
        """Determine the status string for the fix component."""
        # Degraded / failed analysis
        if confidence == 0.0:
            return "analysis_failed"

        if not fixes:
            return "manual_review"

        # Check if any fix has executable content (file edits or shell commands)
        has_executable = any(f.file_edits or f.commands for f in fixes)

        if not has_executable:
            # AI gave recommendations but no code/commands — guidance only
            return "guidance_only"

        # Has executable fixes — check if approval gates are triggered
        if rec.requires_human_review or confidence < _AUTO_APPLY_THRESHOLD:
            return "pending_approval"

        return "fix_available"

    @classmethod
    def _needs_approval(
        cls,
        rec: AIRecommendation,
        fixes: List[FixItem],
        confidence: float,
    ) -> bool:
        """Approval required if: human review flag, low confidence, or high risk fix."""
        if rec.requires_human_review:
            return True
        if confidence < _AUTO_APPLY_THRESHOLD:
            return True
        if any(f.risk in _HIGH_RISK_LEVELS for f in fixes):
            return True
        return False

    @classmethod
    def _build_diagnosis(
        cls,
        rec: AIRecommendation,
        bundle: CorrelationBundle,
    ) -> DiagnosisSummary:
        """Build the human-readable diagnosis block."""
        rca = rec.root_cause_analysis

        # Severity from confidence assessment risk level or top recommendation
        raw_severity = "unknown"
        if rec.confidence_assessment.risk_level:
            raw_severity = rec.confidence_assessment.risk_level.lower()
        elif rec.recommendations:
            raw_severity = (rec.recommendations[0].risk_level or "unknown").lower()
        severity = _SEVERITY_MAP.get(raw_severity, "high")

        # affected_files — echo from git_context if available
        affected_files: List[str] = []
        if bundle.git_context and bundle.git_context.changed_files:
            affected_files = bundle.git_context.changed_files

        return DiagnosisSummary(
            summary=rca.summary or "",
            root_cause=rca.primary_cause or "Unknown",
            severity=severity,
            affected_services=bundle.affectedServices or [],
            affected_files=affected_files,
            causal_chain=rca.timeline or [],
        )

    @classmethod
    def _build_meta(cls, rec: AIRecommendation) -> IncidentMeta:
        """Build audit trail from metadata and similar cases."""
        model_used = None
        processing_time_ms = rec.processing_time_ms

        # model_used is stored in metadata by AIAdapterService
        if rec.metadata:
            model_used = rec.metadata.get("model_used")

        # Collect similar case IDs from all recommendations
        similar_ids: List[str] = []
        seen = set()
        for r in rec.recommendations:
            for sc in (r.similar_cases or []):
                if sc.incident_id not in seen:
                    similar_ids.append(sc.incident_id)
                    seen.add(sc.incident_id)

        rag_count = rec.metadata.get("rag_incidents_used", 0) if rec.metadata else 0

        return IncidentMeta(
            model_used=model_used,
            rag_incidents_used=rag_count,
            similar_cases=similar_ids,
        )
