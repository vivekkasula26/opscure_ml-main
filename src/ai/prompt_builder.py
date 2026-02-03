"""
Prompt Builder Module
Constructs AI prompts from CorrelationBundle and retrieved incidents.
"""

import json
from typing import List
from src.common.types import CorrelationBundle, RetrievedIncident, LogPattern
from src.ai.summarizer import Summarizer
from src.ai.error_correlator import ErrorCorrelator


class PromptBuilder:
    """
    Builds structured prompts for the AI model.
    Combines CorrelationBundle data with RAG context.
    """
    
    SYSTEM_PROMPT = """You are an SRE expert AI. You analyze incidents using logs, metrics, events, and prior historical examples.

Rules:
- Never hallucinate. Only use provided data.
- Be precise about root cause identification.
- Recommend specific, actionable fixes.
- FOR CODE FIXES: Do NOT use `sed` or fragile text manipulation. Use the `file_edit` structure. Provide the `original_context` (exact code block to be replaced, 3-5 lines) and `replacement_text`. This ensures the fix is applied to the correct location even if line numbers shift.
- FOR XML/POM FIXES: Use `fix_type="xml_block_edit"`. Provide `xml_selector` (e.g., "dependency", "plugin") and `xml_value` (e.g., artifactId) to safely remove entire blocks.
- FOR RUNTIME ISSUES: Do NOT invent code fixes for ephemeral problems (e.g., OOM kills, spikes). Use `fix_type="runtime_remediation"` and suggest reversible actions like "restart pod", "clear cache", or "scale up".
- Assess if the fix is safe for automated execution.
- Return ONLY valid JSON in the specified format."""

    OUTPUT_SCHEMA = """{
  "root_cause_analysis": {
    "summary": "string - concise summary of root cause",
    "primary_cause": "string - specific technical cause",
    "contributing_factors": ["string array - list of contributing factors"],
    "timeline": ["string array - key events leading to failure"],
    "evidence": {"key": "value - supporting logs/metrics"},
    "impact": "string - business/system impact"
  },
  "causal_chain": [
    {
      "step": "integer - step number",
      "event": "string - event description",
      "timestamp": "string - ISO timestamp",
      "metric": "string - relevant metric name (optional)",
      "value": "number - metric value (optional)",
      "normal": "number - normal baseline (optional)",
      "anomaly_score": "number - z-score (optional)"
    }
  ],
  "recommendations": [
    {
      "rank": "integer - priority (1 is highest)",
      "title": "string - short title",
      "description": "string - detailed description",
      "fix_type": "string - code_patch, config_change, runtime_remediation, preventive_recommendation",
      "estimated_effort": "string - low/medium/high",
      "estimated_time_minutes": "integer",
      "risk_level": "string - low/medium/high",
      "cost_impact": "string",
      "implementation": {
        "type": "string - e.g. git_workflow, kubectl",
        "commands": ["string array - shell commands"],
        "file_edits": [
          {
            "file_path": "string - absolute path",
            "original_context": "string - exact code block to be replaced (multi-line)",
            "replacement_text": "string - replacement code block (multi-line)",
            "xml_selector": "string - dependency or plugin (only for xml_block_edit)",
            "xml_value": "string - artifactId to remove (only for xml_block_edit)"
          }
        ],
        "pre_checks": ["string array - safety checks"],
        "post_checks": ["string array - verification steps"]
      },
      "rollback": {
        "commands": ["string array - rollback commands"],
        "automatic_rollback_if": ["string array - conditions"],
        "rollback_time_seconds": "integer"
      },
      "reasoning": "string - why this fix was chosen",
      "side_effects": ["string array - potential side effects"],
      "ai_confidence": "number 0.0-1.0"
    }
  ],
  "confidence_assessment": {
    "final_confidence": "number 0.0-1.0",
    "action": "string - auto_heal or manual_review",
    "threshold_used": "number",
    "risk_level": "string",
    "breakdown": {"factor": "number 0.0-1.0"},
    "adjustments": {"bonuses": [], "penalties": []},
    "reasoning": "string - explanation of confidence score",
    "decision_factors": {"key": "value"}
  },
  "requires_human_review": "boolean",
  "auto_heal_candidate": "boolean"
}"""

    @classmethod
    def build_prompt(
        cls,
        bundle: CorrelationBundle,
        similar_incidents: List[RetrievedIncident]
    ) -> str:
        """
        Build a complete prompt for AI analysis.
        
        Args:
            bundle: The correlation bundle to analyze
            similar_incidents: Historical incidents from RAG
            
        Returns:
            Formatted prompt string for the AI model
        """
        # Build correlation bundle section
        bundle_json = cls._format_bundle_for_prompt(bundle)
        
        # Build similar incidents section
        similar_json = cls._format_similar_incidents(similar_incidents)
        
        # Construct user prompt
        user_prompt = f"""Analyze this incident correlation bundle and provide a diagnosis.

## CorrelationBundle

```json
{bundle_json}
```

## Similar Historical Incidents

```json
{similar_json}
```

## Instructions

1. Analyze the log patterns, events, and metric anomalies
2. Consider the similar historical incidents for context
3. Identify the most likely root cause
4. Determine the causal chain of failures
5. Recommend a specific action to resolve the issue
6. Assess if automated execution is safe

Return ONLY valid JSON matching this schema:

```json
{cls.OUTPUT_SCHEMA}
```

Your response (JSON only, no markdown, no explanation):"""

        return user_prompt
    
    @classmethod
    def build_full_prompt(
        cls,
        bundle: CorrelationBundle,
        similar_incidents: List[RetrievedIncident]
    ) -> dict:
        """
        Build prompt as messages array for chat-based models.
        
        Args:
            bundle: The correlation bundle to analyze
            similar_incidents: Historical incidents from RAG
            
        Returns:
            Dict with system and user messages
        """
        user_prompt = cls.build_prompt(bundle, similar_incidents)
        
        return {
            "system": cls.SYSTEM_PROMPT,
            "user": user_prompt
        }
    
    @classmethod
    def _format_bundle_for_prompt(cls, bundle: CorrelationBundle) -> str:
        """
        Format CorrelationBundle as JSON for the prompt.
        Includes all relevant fields while keeping it readable.
        
        Args:
            bundle: The correlation bundle
            
        Returns:
            Formatted JSON string
        """
        # Create a condensed representation
        prompt_bundle = {
            "id": bundle.id,
            "window": {
                "start": bundle.windowStart,
                "end": bundle.windowEnd
            },
            "rootService": bundle.rootService,
            "affectedServices": bundle.affectedServices,
            "errorCorrelation": cls._format_correlated_patterns(
                bundle.logPatterns, 
                bundle.dependencyGraph
            ),
            "events": [
                {
                    "type": e.type,
                    "reason": e.reason,
                    "service": e.service,
                    "pod": e.pod
                }
                for e in bundle.events[:10]  # Limit to 10 events
            ],
            "metrics": {
                "cpuZ": bundle.metrics.cpuZ,
                "memZ": bundle.metrics.memZ,
                "latencyZ": bundle.metrics.latencyZ,
                "errorRateZ": bundle.metrics.errorRateZ
            },

            "dependencyGraph": bundle.dependencyGraph,
            "sequence": [
                {
                    "timestamp": s.timestamp,
                    "type": s.type,
                    "message": s.message[:200], # Truncate individual messages
                    "idx": s.sequenceIndex
                }
                for s in bundle.sequence[:50] # Limit to 50 items to preserve context window
            ],
            "derivedRootCauseHint": bundle.derivedRootCauseHint,
            "gitContext": {
                "repo": bundle.git_context.repo_url if bundle.git_context else None,
                "branch": bundle.git_context.branch if bundle.git_context else None,
                "recentCommits": bundle.git_context.recent_commits if bundle.git_context else [],
                "userConfig": {
                    "name": bundle.git_config.user_name if bundle.git_config else None,
                    "email": bundle.git_config.user_email if bundle.git_config else None
                } if bundle.git_config else None,
                "configFiles": {
                    "local": bundle.git_config.local_config_content if bundle.git_config else None,
                    "global": bundle.git_config.global_config_content if bundle.git_config else None
                } if bundle.git_config else None
            } if bundle.git_context or bundle.git_config else None,
            "codeSnippets": [
                {
                    "file": s.file_path,
                    "lines": f"{s.start_line}-{s.end_line}",
                    "content": s.content
                }
                for s in bundle.code_snippets
            ]
        }
        
        # Remove None values for cleaner output
        prompt_bundle = cls._remove_none_values(prompt_bundle)
        
        return json.dumps(prompt_bundle, indent=2)
    
    @classmethod
    def _format_similar_incidents(cls, incidents: List[RetrievedIncident]) -> str:
        """
        Format similar incidents for RAG context.
        
        Args:
            incidents: List of retrieved historical incidents
            
        Returns:
            Formatted JSON string
        """
        if not incidents:
            return "[]"
        
        formatted = [
            {
                "id": inc.id,
                "summary": inc.summary,
                "rootCause": inc.rootCause,
                "recommendedAction": inc.recommendedAction,
                "similarityScore": round(inc.confidence, 2)
            }
            for inc in incidents
        ]
        
        return json.dumps(formatted, indent=2)
    
    @classmethod
    def _remove_none_values(cls, obj):
        """
        Recursively remove None values from a dict.
        
        Args:
            obj: Dictionary to clean
            
        Returns:
            Cleaned dictionary
        """
        if isinstance(obj, dict):
            return {
                k: cls._remove_none_values(v)
                for k, v in obj.items()
                if v is not None
            }
        elif isinstance(obj, list):
            return [cls._remove_none_values(item) for item in obj]
        else:
            return obj
    
    @classmethod
    def _format_correlated_patterns(
        cls, 
        patterns: List[LogPattern], 
        dependency_graph: List[str]
    ) -> dict:
        """
        Use ErrorCorrelator to group related errors and identify MULTIPLE root causes.
        
        Returns structured format for AI consumption with ranked root causes.
        """
        if not patterns:
            return {"primaryCluster": None, "secondaryClusters": [], "unrelatedPatterns": []}
        
        # Run correlation
        result = ErrorCorrelator.correlate(patterns, dependency_graph)
        
        def format_pattern(p) -> dict:
            return {
                "pattern": p.pattern[:500],
                "count": p.count,
                "errorClass": p.errorClass,
                "firstOccurrence": p.firstOccurrence,
                "logSource": {
                    "type": p.logSource.type if p.logSource else None,
                    "file": p.logSource.file if p.logSource else None
                } if p.logSource else None
            }
        
        def format_ranked_cause(rc) -> dict:
            pattern = rc.pattern
            return {
                "rank": rc.rank,
                "severity": rc.severity_score,
                "pattern": pattern.pattern[:500],
                "errorClass": pattern.errorClass,
                "reason": rc.reason,
                "logSource": pattern.logSource.type if pattern.logSource else None
            }
        
        def format_cluster(cluster) -> dict:
            # Include all ranked root causes
            ranked_causes = [format_ranked_cause(rc) for rc in cluster.root_causes] if cluster.root_causes else []
            
            return {
                "timestamp": cluster.timestamp,
                "rootCauses": ranked_causes,  # Multiple ranked causes
                "primaryRootCause": format_pattern(cluster.root_cause) if cluster.root_cause else None,  # Backward compat
                "effects": [format_pattern(p) for p in cluster.effects[:5]]
            }
        
        return {
            "primaryCluster": format_cluster(result.primary_cluster) if result.primary_cluster else None,
            "secondaryClusters": [format_cluster(c) for c in result.secondary_clusters[:3]],
            "unrelatedPatterns": [format_pattern(p) for p in result.unrelated_patterns[:5]]
        }
    
    @classmethod
    def build_simple_prompt(cls, bundle: CorrelationBundle) -> str:
        """
        Build a simple prompt without RAG context.
        Useful for testing or when Pinecone is unavailable.
        
        Args:
            bundle: The correlation bundle
            
        Returns:
            Simple prompt string
        """
        summary = Summarizer.summarize_for_prompt(bundle)
        
        return f"""Analyze this incident and provide a diagnosis.

## Incident Summary

{summary}

## Instructions

Identify the root cause and recommend an action.

Return ONLY valid JSON:

```json
{cls.OUTPUT_SCHEMA}
```

Your response (JSON only):"""

    @classmethod
    def _get_prioritized_patterns(cls, patterns: List[LogPattern], limit: int = 20) -> List[LogPattern]:
        """
        Sort and filter log patterns based on severity and count.
        Prioritizes Critical/Fatal errors over noise.
        
        Args:
            patterns: List of log patterns
            limit: Maximum number of patterns to return
            
        Returns:
            Sorted and filtered list of patterns
        """
        if not patterns:
            return []
            
        # Sort by:
        # 1. Severity (Higher is better)
        # 2. Count (Higher is better)
        # 3. Time (Later is better? Or just stable sort)
        
        # We need a stable sort key
        def sort_key(p: LogPattern):
            severity = cls._calculate_pattern_severity(p)
            return (severity, p.count)
            
        # Sort descending
        sorted_patterns = sorted(patterns, key=sort_key, reverse=True)
        
        return sorted_patterns[:limit]
        
    @classmethod
    def _calculate_pattern_severity(cls, pattern: LogPattern) -> int:
        """
        Calculate severity score for a log pattern.
        
        Score mapping:
        - 100: Critical, Fatal, Panic
        - 80: Error, Exception, Fail
        - 50: Warning, Warn
        - 10: Info, Debug, Trace (Default)
        
        Args:
            pattern: The log pattern to score
            
        Returns:
            Integer severity score
        """
        text = pattern.pattern.lower()
        if pattern.errorClass:
            text += " " + pattern.errorClass.lower()
            
        if any(w in text for w in ["fatal", "panic", "critical", "emerg"]):
            return 100
        if any(w in text for w in ["error", "exception", "fail", "crash", "unhandled"]):
            return 80
        if any(w in text for w in ["warning", "warn"]):
            return 50
            
        return 10
