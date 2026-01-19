"""
Summarizer Module
Builds short textual summaries from CorrelationBundle for Pinecone embeddings.
"""

from typing import List
from src.common.types import CorrelationBundle


class Summarizer:
    """
    Creates concise textual summaries of CorrelationBundle for embedding.
    Summaries are optimized for semantic similarity search.
    """
    
    @staticmethod
    def summarize_bundle(bundle: CorrelationBundle) -> str:
        """
        Build a short summary from CorrelationBundle.
        
        Highlights:
        - Root service (if identified)
        - Error classes found
        - Key anomaly metrics
        - Key events
        
        Args:
            bundle: The correlation bundle to summarize
            
        Returns:
            A concise textual summary for embedding
        """
        parts: List[str] = []
        
        # Root service
        if bundle.rootService:
            parts.append(f"Root service: {bundle.rootService}")
        
        # Affected services
        if bundle.affectedServices:
            services = ", ".join(bundle.affectedServices[:5])
            parts.append(f"Affected services: {services}")
        
        # Error classes from log patterns
        error_classes = set()
        for pattern in bundle.logPatterns:
            if pattern.errorClass:
                error_classes.add(pattern.errorClass)
        
        if error_classes:
            classes = ", ".join(list(error_classes)[:5])
            parts.append(f"Error classes: {classes}")
        
        # Top log patterns by count
        if bundle.logPatterns:
            sorted_patterns = sorted(bundle.logPatterns, key=lambda p: p.count, reverse=True)
            top_patterns = sorted_patterns[:3]
            for pattern in top_patterns:
                parts.append(f"Log pattern ({pattern.count}x): {pattern.pattern[:500]}")
        
        # Anomaly metrics
        anomalies = []
        if bundle.metrics.cpuZ and abs(bundle.metrics.cpuZ) > 2.0:
            anomalies.append(f"CPU Z-score: {bundle.metrics.cpuZ:.2f}")
        if bundle.metrics.memZ and abs(bundle.metrics.memZ) > 2.0:
            anomalies.append(f"Memory Z-score: {bundle.metrics.memZ:.2f}")
        if bundle.metrics.latencyZ and abs(bundle.metrics.latencyZ) > 2.0:
            anomalies.append(f"Latency Z-score: {bundle.metrics.latencyZ:.2f}")
        if bundle.metrics.errorRateZ and abs(bundle.metrics.errorRateZ) > 2.0:
            anomalies.append(f"Error rate Z-score: {bundle.metrics.errorRateZ:.2f}")
        
        if anomalies:
            parts.append(f"Anomalies: {'; '.join(anomalies)}")
        
        # Key events
        if bundle.events:
            event_types = set(e.type for e in bundle.events[:5])
            event_reasons = set(e.reason for e in bundle.events[:5])
            parts.append(f"Event types: {', '.join(event_types)}")
            parts.append(f"Event reasons: {', '.join(event_reasons)}")
        
        # Derived hint
        if bundle.derivedRootCauseHint:
            parts.append(f"Hint: {bundle.derivedRootCauseHint}")
        
        # Dependency chain
        if bundle.dependencyGraph:
            chain = " → ".join(bundle.dependencyGraph[:5])
            parts.append(f"Dependency chain: {chain}")
        
        # Join all parts
        summary = " | ".join(parts)
        
        # Truncate if too long (for embedding limits)
        if len(summary) > 5000:
            summary = summary[:5000] + "..."
        
        return summary
    
    @staticmethod
    def summarize_for_prompt(bundle: CorrelationBundle) -> str:
        """
        Create a more detailed summary for inclusion in the AI prompt.
        This is longer than the embedding summary.
        
        Args:
            bundle: The correlation bundle to summarize
            
        Returns:
            A detailed textual summary for the AI prompt
        """
        lines: List[str] = []
        
        lines.append(f"Correlation Window: {bundle.windowStart} to {bundle.windowEnd}")
        
        if bundle.rootService:
            lines.append(f"Identified Root Service: {bundle.rootService}")
        
        if bundle.affectedServices:
            lines.append(f"Affected Services: {', '.join(bundle.affectedServices)}")
        
        # Log patterns
        if bundle.logPatterns:
            lines.append("\nLog Patterns:")
            for pattern in bundle.logPatterns[:5]:
                error_info = f" [{pattern.errorClass}]" if pattern.errorClass else ""
                lines.append(f"  - ({pattern.count}x){error_info}: {pattern.pattern[:1000]}")
        
        # Events
        if bundle.events:
            lines.append("\nKey Events:")
            for event in bundle.events[:5]:
                pod_info = f" (pod: {event.pod})" if event.pod else ""
                lines.append(f"  - [{event.type}] {event.reason}{pod_info}")
        
        # Metrics
        lines.append("\nMetric Anomalies:")
        if bundle.metrics.cpuZ:
            lines.append(f"  - CPU Z-score: {bundle.metrics.cpuZ:.2f}")
        if bundle.metrics.memZ:
            lines.append(f"  - Memory Z-score: {bundle.metrics.memZ:.2f}")
        if bundle.metrics.latencyZ:
            lines.append(f"  - Latency Z-score: {bundle.metrics.latencyZ:.2f}")
        if bundle.metrics.errorRateZ:
            lines.append(f"  - Error Rate Z-score: {bundle.metrics.errorRateZ:.2f}")
        
        # Dependency graph
        if bundle.dependencyGraph:
            lines.append(f"\nDependency Chain: {' → '.join(bundle.dependencyGraph)}")
        
        # Derived hint
        if bundle.derivedRootCauseHint:
            lines.append(f"\nDerived Root Cause Hint: {bundle.derivedRootCauseHint}")
        
        return "\n".join(lines)

