"""
Error Correlator Module

Groups related errors using:
1. Temporal Clustering - errors that occur within the same time window
2. Dependency Graph Ranking - identifies root cause based on service dependencies
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from src.common.types import LogPattern


@dataclass
class RankedCause:
    """A root cause with ranking information"""
    pattern: LogPattern
    rank: int
    severity_score: int
    dependency_score: int
    reason: str  # Why this is considered a root cause


@dataclass
class ErrorCluster:
    """A group of related errors occurring together"""
    cluster_id: str
    timestamp: str  # Cluster start time
    patterns: List[LogPattern] = field(default_factory=list)
    # Multiple ranked root causes (sorted by priority)
    root_causes: List[RankedCause] = field(default_factory=list)
    # Legacy single root_cause for backward compatibility
    root_cause: Optional[LogPattern] = None
    effects: List[LogPattern] = field(default_factory=list)


@dataclass 
class CorrelationResult:
    """Result of error correlation analysis"""
    primary_cluster: Optional[ErrorCluster] = None
    secondary_clusters: List[ErrorCluster] = field(default_factory=list)
    unrelated_patterns: List[LogPattern] = field(default_factory=list)


class ErrorCorrelator:
    """
    Correlates errors using temporal clustering and dependency graph analysis.
    
    Phase 1: Temporal Clustering
    - Group patterns by firstOccurrence timestamp within a window
    
    Phase 2: Dependency Graph Ranking  
    - Within each cluster, identify root cause using dependency chain
    
    Phase 3 (NEW): Auto-Extract Dependencies
    - If no dependency graph provided, extract from logs/stack traces
    """
    
    # Default clustering window in seconds
    DEFAULT_CLUSTER_WINDOW_SECONDS = 2.0
    
    @classmethod
    def correlate(
        cls,
        patterns: List[LogPattern],
        dependency_graph: Optional[List[str]] = None,
        cluster_window_seconds: float = DEFAULT_CLUSTER_WINDOW_SECONDS,
        auto_extract_deps: bool = True
    ) -> CorrelationResult:
        """
        Main entry point: cluster errors by time, then rank by dependency.
        
        Args:
            patterns: List of log patterns from CorrelationBundle
            dependency_graph: Service dependency chain (optional - will auto-extract if None)
            cluster_window_seconds: Time window for grouping (default 2s)
            auto_extract_deps: If True, auto-extract deps when graph is empty/None
            
        Returns:
            CorrelationResult with primary cluster and root causes identified
        """
        if not patterns:
            return CorrelationResult()
        
        # Phase 0: Auto-extract dependencies if not provided
        effective_graph = dependency_graph or []
        extracted_graph = None
        
        if not effective_graph and auto_extract_deps:
            from src.ai.dependency_extractor import DependencyExtractor
            extracted = DependencyExtractor.extract_from_patterns(patterns)
            effective_graph = extracted.nodes
            extracted_graph = extracted
            print(f"[ErrorCorrelator] Auto-extracted {len(effective_graph)} dependencies: {effective_graph[:5]}...")
        
        # Phase 1: Temporal Clustering
        clusters = cls.cluster_by_time(patterns, cluster_window_seconds)
        
        # Phase 2: Dependency Graph Ranking (for each cluster)
        for cluster in clusters:
            cls.rank_by_dependency(cluster, effective_graph)
        
        # Sort clusters by severity (highest severity root cause first)
        clusters.sort(
            key=lambda c: cls._get_severity_score(c.root_cause) if c.root_cause else 0,
            reverse=True
        )
        
        # Identify primary vs secondary clusters
        result = CorrelationResult()
        if clusters:
            result.primary_cluster = clusters[0]
            result.secondary_clusters = clusters[1:] if len(clusters) > 1 else []
        
        return result
    
    @classmethod
    def cluster_by_time(
        cls,
        patterns: List[LogPattern],
        window_seconds: float = 2.0
    ) -> List[ErrorCluster]:
        """
        Phase 1: Group patterns by time proximity.
        
        Patterns whose firstOccurrence is within window_seconds of each other
        are grouped into the same cluster.
        """
        if not patterns:
            return []
        
        # Sort by firstOccurrence
        sorted_patterns = sorted(
            patterns,
            key=lambda p: cls._parse_timestamp(p.firstOccurrence) or datetime.min
        )
        
        clusters: List[ErrorCluster] = []
        current_cluster: Optional[ErrorCluster] = None
        last_time: Optional[datetime] = None
        
        for pattern in sorted_patterns:
            pattern_time = cls._parse_timestamp(pattern.firstOccurrence)
            
            if pattern_time is None:
                # No timestamp - create standalone cluster
                clusters.append(ErrorCluster(
                    cluster_id=f"cluster_{len(clusters)}",
                    timestamp=pattern.firstOccurrence,
                    patterns=[pattern]
                ))
                continue
            
            # Check if within window of current cluster
            if current_cluster and last_time:
                delta = (pattern_time - last_time).total_seconds()
                if delta <= window_seconds:
                    # Add to current cluster
                    current_cluster.patterns.append(pattern)
                    last_time = pattern_time
                    continue
            
            # Start new cluster
            current_cluster = ErrorCluster(
                cluster_id=f"cluster_{len(clusters)}",
                timestamp=pattern.firstOccurrence,
                patterns=[pattern]
            )
            clusters.append(current_cluster)
            last_time = pattern_time
        
        return clusters
    
    @classmethod
    def rank_by_dependency(
        cls,
        cluster: ErrorCluster,
        dependency_graph: List[str],
        max_root_causes: int = 5
    ) -> None:
        """
        Phase 2: Within a cluster, identify MULTIPLE root causes ranked by priority.
        
        Ranking factors:
        1. Severity (FATAL > ERROR > WARNING > INFO)
        2. Dependency depth (deeper in chain = more likely root cause)
        3. Error class presence
        
        Modifies cluster in place, setting root_causes list.
        """
        if not cluster.patterns:
            return
        
        # Build dependency priority map
        dep_priority = {}
        if dependency_graph:
            dep_priority = {svc.lower(): i for i, svc in enumerate(reversed(dependency_graph))}
        
        # Score each pattern
        scored_patterns: List[Tuple[LogPattern, int, int, str]] = []
        
        for pattern in cluster.patterns:
            severity = cls._get_severity_score(pattern)
            dep_score = cls._get_dependency_score(pattern, dep_priority)
            reason = cls._get_ranking_reason(pattern, severity, dep_score)
            
            # Only consider patterns with some severity (not just INFO)
            if severity >= 50 or dep_score > 0:  # WARNING and above, or has dependency match
                scored_patterns.append((pattern, severity, dep_score, reason))
        
        # Sort by (severity, dependency_score) descending
        scored_patterns.sort(key=lambda x: (x[1], x[2]), reverse=True)
        
        # Build ranked root causes
        cluster.root_causes = []
        for rank, (pattern, severity, dep_score, reason) in enumerate(scored_patterns[:max_root_causes], 1):
            cluster.root_causes.append(RankedCause(
                pattern=pattern,
                rank=rank,
                severity_score=severity,
                dependency_score=dep_score,
                reason=reason
            ))
        
        # Set primary root_cause for backward compatibility
        if cluster.root_causes:
            cluster.root_cause = cluster.root_causes[0].pattern
        
        # Everything not a root cause is an effect
        root_cause_patterns = {rc.pattern.pattern for rc in cluster.root_causes}
        cluster.effects = [p for p in cluster.patterns if p.pattern not in root_cause_patterns]
    
    @classmethod
    def _get_dependency_score(cls, pattern: LogPattern, dep_priority: Dict[str, int]) -> int:
        """Calculate dependency depth score for a pattern"""
        if not dep_priority:
            return 0
        
        pattern_text = pattern.pattern.lower()
        best_score = 0
        
        for svc, priority in dep_priority.items():
            if svc in pattern_text:
                best_score = max(best_score, priority)
        
        return best_score
    
    @classmethod
    def _get_ranking_reason(cls, pattern: LogPattern, severity: int, dep_score: int) -> str:
        """Generate human-readable reason for ranking"""
        reasons = []
        
        if severity >= 100:
            reasons.append("CRITICAL/FATAL severity")
        elif severity >= 80:
            reasons.append("ERROR level")
        elif severity >= 50:
            reasons.append("WARNING level")
        
        if dep_score > 0:
            reasons.append(f"deep in dependency chain (depth={dep_score})")
        
        if pattern.count > 1:
            reasons.append(f"occurred {pattern.count}x")
        
        return "; ".join(reasons) if reasons else "pattern detected"
    
    @classmethod
    def _parse_timestamp(cls, ts: str) -> Optional[datetime]:
        """Parse ISO timestamp string to datetime"""
        if not ts:
            return None
        
        try:
            # Handle various formats
            ts_clean = ts.replace('Z', '+00:00')
            if '.' in ts_clean:
                # Truncate microseconds to 6 digits
                parts = ts_clean.split('.')
                if len(parts) == 2:
                    micro_part = parts[1]
                    tz_idx = micro_part.find('+')
                    if tz_idx == -1:
                        tz_idx = micro_part.find('-')
                    if tz_idx > 0:
                        micro = micro_part[:tz_idx][:6].ljust(6, '0')
                        tz = micro_part[tz_idx:]
                        ts_clean = f"{parts[0]}.{micro}{tz}"
                    else:
                        ts_clean = f"{parts[0]}.{micro_part[:6].ljust(6, '0')}"
                        
            return datetime.fromisoformat(ts_clean.replace('+00:00', ''))
        except (ValueError, AttributeError):
            return None
    
    @classmethod
    def _get_severity_score(cls, pattern: Optional[LogPattern]) -> int:
        """Calculate severity score for a pattern"""
        if not pattern:
            return 0
        
        text = pattern.pattern.lower()
        if pattern.errorClass:
            text += " " + pattern.errorClass.lower()
        
        if any(w in text for w in ["fatal", "panic", "critical", "emerg"]):
            return 100
        if any(w in text for w in ["error", "exception", "fail", "crash"]):
            return 80
        if any(w in text for w in ["warning", "warn"]):
            return 50
        return 10
