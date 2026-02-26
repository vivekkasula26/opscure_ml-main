"""
Log Preprocessor - Transforms raw logs into CorrelationBundle
Algorithm-based (regex, hash map, sliding window) - No ML required
"""

import re
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import hashlib


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class LogSource:
    type: str           # "application" | "init" | "access" | "gc" | "system" | "audit"
    file: str = ""
    container: str = ""
    namespace: str = ""
    node: str = ""
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class ParsedLog:
    timestamp: datetime
    level: str          # ERROR, WARNING, INFO
    message: str        # Full message including stack trace
    log_source: LogSource
    raw_line: str = ""


@dataclass
class LogPattern:
    pattern: str
    count: int
    first_occurrence: str
    last_occurrence: str
    error_class: str
    log_source: LogSource
    root_service: str = ""  # Stamped by BundleBuilder — the identified root cause service

    def to_dict(self) -> dict:
        # Derive the clean service name for this specific pattern
        affected_service = None
        if self.log_source and self.log_source.container:
            svc = re.sub(r'-[a-f0-9]+-[a-z0-9]+$', '', self.log_source.container)
            svc = re.sub(r'-\d+$', '', svc)
            affected_service = svc

        return {
            "pattern": self.pattern,
            "count": self.count,
            "firstOccurrence": self.first_occurrence,
            "lastOccurrence": self.last_occurrence,
            "severity": self.error_class,
            "rootService": self.root_service or None,    # Root cause service for this pattern
            "affectedService": affected_service,          # Service that produced this log
            "logSource": self.log_source.to_dict()
        }


# =============================================================================
# LOG PARSER - Regex-based
# =============================================================================

class LogParser:
    """Parse raw log lines into structured entries. Groups multi-line stack traces."""
    
    # Timestamp patterns
    TIMESTAMP_PATTERNS = [
        (r'^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?)', '%Y-%m-%dT%H:%M:%S'),
        (r'^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}(?:\.\d+)?)', '%Y-%m-%d %H:%M:%S'),
        (r'^\[(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})', '%Y-%m-%dT%H:%M:%S'),
    ]
    
    # Stack trace continuation patterns (lines that are part of stack trace)
    STACK_CONTINUATION = [
        r'^\s+at\s+',           # Java: "    at com.example.Class.method"
        r'^\s+File\s+"',        # Python: '  File "/path", line 10'
        r'^\s+\.\.\.\s+\d+',    # Java: "    ... 15 more"
        r'^Caused\s+by:',       # Exception chains
        r'^\s+\^',              # Python arrow indicator
    ]
    
    @classmethod
    def is_new_log_entry(cls, line: str) -> bool:
        """Check if line starts a new log entry (has timestamp)"""
        for pattern, _ in cls.TIMESTAMP_PATTERNS:
            if re.match(pattern, line.strip()):
                return True
        return False
    
    @classmethod
    def is_stack_continuation(cls, line: str) -> bool:
        """Check if line is part of a stack trace"""
        for pattern in cls.STACK_CONTINUATION:
            if re.match(pattern, line):
                return True
        return False
    
    @classmethod
    def extract_timestamp(cls, line: str) -> Optional[datetime]:
        """Extract and parse timestamp from log line"""
        for pattern, fmt in cls.TIMESTAMP_PATTERNS:
            match = re.search(pattern, line)
            if match:
                ts_str = match.group(1).replace('T', ' ').split('.')[0]
                try:
                    return datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
                except:
                    pass
        return datetime.now()
    
    @classmethod
    def extract_level(cls, line: str) -> str:
        """Extract log level from line"""
        upper = line.upper()
        if re.search(r'\b(ERROR|FATAL|CRITICAL|EXCEPTION)\b', upper):
            return "ERROR"
        if re.search(r'\b(WARN|WARNING)\b', upper):
            return "WARNING"
        return "INFO"
    
    @classmethod
    def parse(cls, raw_lines: List[str], log_source: LogSource) -> List[ParsedLog]:
        """
        Parse raw lines into structured entries.
        CRITICAL: Multi-line stack traces are grouped together!
        """
        parsed = []
        current_entry: Optional[ParsedLog] = None
        
        for line in raw_lines:
            if not line.strip():
                continue
                
            if cls.is_new_log_entry(line):
                # Save previous entry
                if current_entry:
                    parsed.append(current_entry)
                
                # Start new entry
                current_entry = ParsedLog(
                    timestamp=cls.extract_timestamp(line),
                    level=cls.extract_level(line),
                    message=line,
                    log_source=log_source,
                    raw_line=line
                )
            elif cls.is_stack_continuation(line) or (current_entry and not cls.is_new_log_entry(line)):
                # Stack trace continuation - APPEND to current entry
                if current_entry:
                    current_entry.message += "\n" + line
        
        # Don't forget last entry
        if current_entry:
            parsed.append(current_entry)
        
        return parsed


# =============================================================================
# PATTERN DEDUPLICATOR - Hash Map based
# =============================================================================

class PatternDeduplicator:
    """Group similar logs and count occurrences using hash-based deduplication."""
    
    @classmethod
    def normalize_for_hash(cls, message: str) -> str:
        """Replace variable parts with placeholders for grouping"""
        result = message
        
        # UUIDs
        result = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', '<UUID>', result, flags=re.I)
        
        # IP addresses
        result = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>', result)
        
        # Common IDs
        result = re.sub(r'(?:user_?id|order_?id|request_?id|session_?id|id)[=:]\s*\w+', 'id=<ID>', result, flags=re.I)
        
        # Large numbers (but keep line numbers in stack traces)
        result = re.sub(r'(?<![:\(])\b\d{6,}\b(?!\))', '<NUM>', result)
        
        # Timestamps in message
        result = re.sub(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', '<TS>', result)
        
        return result
    
    @classmethod
    def deduplicate(cls, logs: List[ParsedLog]) -> List[LogPattern]:
        """Group similar logs, count occurrences, track first/last time."""
        patterns: Dict[str, dict] = {}
        
        for log in logs:
            # Create hash key from normalized message
            normalized = cls.normalize_for_hash(log.message)
            key = hashlib.md5(normalized.encode()).hexdigest()
            
            ts_str = log.timestamp.isoformat() + "Z"
            
            if key in patterns:
                patterns[key]["count"] += 1
                patterns[key]["last_occurrence"] = ts_str
            else:
                patterns[key] = {
                    "pattern": log.message,  # Keep ORIGINAL
                    "count": 1,
                    "first_occurrence": ts_str,
                    "last_occurrence": ts_str,
                    "error_class": log.level,
                    "log_source": log.log_source
                }
        
        # Convert to LogPattern objects, sorted by severity
        result = [
            LogPattern(
                pattern=p["pattern"],
                count=p["count"],
                first_occurrence=p["first_occurrence"],
                last_occurrence=p["last_occurrence"],
                error_class=p["error_class"],
                log_source=p["log_source"]
            )
            for p in patterns.values()
        ]
        
        # Sort: ERROR first, then WARNING, then INFO
        severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        result.sort(key=lambda p: (severity_order.get(p.error_class, 3), -p.count))
        
        return result


# =============================================================================
# CONTEXT CAPTURE - Sliding Window / Ring Buffer
# =============================================================================

class LogContextCapture:
    """
    Captures logs in a sliding window.
    When ERROR detected, grabs all context (INFO, WARN) from last N minutes.
    """
    
    def __init__(self, lookback_minutes: int = 5, max_entries: int = 10000):
        self.lookback_minutes = lookback_minutes
        self.buffer: deque = deque(maxlen=max_entries)
    
    def add_log(self, log: ParsedLog):
        """Add log to buffer"""
        self.buffer.append(log)
        self._prune_old()
    
    def add_logs(self, logs: List[ParsedLog]):
        """Add multiple logs to buffer"""
        for log in logs:
            self.add_log(log)
    
    def on_error_detected(self, error_log: ParsedLog) -> List[ParsedLog]:
        """
        When ERROR detected, return all logs from lookback window.
        Includes INFO + WARN + ERROR.
        """
        cutoff = error_log.timestamp - timedelta(minutes=self.lookback_minutes)
        
        context = [
            log for log in self.buffer
            if log.timestamp >= cutoff
        ]
        
        return context
    
    def _prune_old(self):
        """Remove entries older than lookback window + buffer"""
        if not self.buffer:
            return
        cutoff = datetime.now() - timedelta(minutes=self.lookback_minutes + 5)
        while self.buffer and self.buffer[0].timestamp < cutoff:
            self.buffer.popleft()


# =============================================================================
# BUNDLE BUILDER
# =============================================================================

class BundleBuilder:
    """Assembles the final CorrelationBundle JSON."""
    
    @classmethod
    def build(
        cls,
        patterns: List[LogPattern],
        root_service: str,
        events: List[dict] = None,
        metrics: dict = None,
        git_config: dict = None
    ) -> dict:
        """Build the CorrelationBundle"""
        from datetime import datetime
        import uuid
        
        # Calculate time window from patterns
        all_times = []
        for p in patterns:
            all_times.append(p.first_occurrence)
            all_times.append(p.last_occurrence)
        
        window_start = min(all_times) if all_times else datetime.now().isoformat() + "Z"
        window_end = max(all_times) if all_times else datetime.now().isoformat() + "Z"
        
        # Stamp root_service on every pattern so each carries full context
        for p in patterns:
            p.root_service = root_service

        return {
            "bundle": {
                "id": f"incident_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
                "windowStart": window_start,
                "windowEnd": window_end,
                "rootService": root_service,
                "affectedServices": cls._extract_affected_services(patterns),

                "logPatterns": [p.to_dict() for p in patterns],
                
                "events": events or [],
                
                "metrics": metrics or {
                    "cpuZ": None,
                    "memZ": None,
                    "latencyZ": None,
                    "errorRateZ": None
                },
                
                "dependencyGraph": None,  # Auto-extracted by Opscure
                
                "git_config": git_config or {
                    "user_name": "ops-bot",
                    "user_email": "ops@company.com"
                }
            },
            "use_rag": True,
            "top_k": 5
        }
    
    @classmethod
    def _extract_affected_services(cls, patterns: List[LogPattern]) -> List[str]:
        """Extract unique service names from ERROR/WARNING patterns only.
        INFO logs are intentionally excluded — they don't indicate a service failure.
        """
        services = set()
        for p in patterns:
            # Skip INFO — only ERROR and WARNING indicate an affected service
            if p.error_class not in ("ERROR", "WARNING"):
                continue
            if p.log_source and p.log_source.container:
                # Clean K8s pod name → service name
                # e.g. "payment-service-7f4d9b-xkz2p" → "payment-service"
                svc = re.sub(r'-[a-f0-9]+-[a-z0-9]+$', '', p.log_source.container)
                svc = re.sub(r'-\d+$', '', svc)
                services.add(svc)
        return list(services)


# =============================================================================
# MAIN PREPROCESSOR
# =============================================================================

class LogPreprocessor:
    """
    Main class: Raw logs → CorrelationBundle
    
    Usage:
        preprocessor = LogPreprocessor(lookback_minutes=5)
        
        # Add logs continuously
        for log_line in log_stream:
            bundle = preprocessor.process_line(log_line, log_source)
            if bundle:  # Bundle created on ERROR
                send_to_opscure(bundle)
    """
    
    def __init__(self, lookback_minutes: int = 5, root_service: str = "unknown"):
        self.lookback_minutes = lookback_minutes
        self.root_service = root_service
        self.context_capture = LogContextCapture(lookback_minutes)
        self.pending_events: List[dict] = []
        self.current_metrics: dict = {}
        self.git_config: dict = {}
    
    def process_lines(
        self,
        raw_lines: List[str],
        log_source: LogSource
    ) -> Optional[dict]:
        """
        Process multiple raw log lines.
        Returns bundle if ERROR detected.
        """
        # 1. Parse lines
        parsed = LogParser.parse(raw_lines, log_source)
        
        # 2. Add to context buffer
        self.context_capture.add_logs(parsed)
        
        # 3. Check for errors
        errors = [l for l in parsed if l.level == "ERROR"]
        
        if errors:
            # Get context (last N minutes including INFO + WARN)
            context = self.context_capture.on_error_detected(errors[0])
            
            # Deduplicate patterns
            patterns = PatternDeduplicator.deduplicate(context)
            
            # Build bundle
            # Build bundle
            return BundleBuilder.build(
                patterns=patterns,
                root_service=self.root_service,
                events=self.pending_events,
                metrics=self.current_metrics,
                git_config=self.git_config
            )
        
        return None
    
    def add_event(self, event: dict):
        """Add external event (K8s, alert)"""
        self.pending_events.append(event)
    
    def set_metrics(self, metrics: dict):
        """Set current metrics"""
        self.current_metrics = metrics
    
    def set_git_config(self, config: dict):
        """Set git configuration for auto-healing"""
        self.git_config = config


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    from datetime import datetime, timedelta
    now = datetime.now()
    t = lambda offset_secs: (now - timedelta(seconds=offset_secs)).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    raw_logs = f"""
{t(180)} INFO Request received POST /api/checkout
{t(90)} WARN HikariPool-1 - Connection pool approaching limit: 48/50 active
{t(60)} WARN HikariPool-1 - Connection pool approaching limit: 49/50 active
{t(30)} ERROR java.sql.SQLException: Cannot acquire connection from pool
    at com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:89)
    at com.example.user.UserRepository.findById(UserRepository.java:45)
    at com.example.payment.PaymentService.process(PaymentService.java:67)
Caused by: java.sql.SQLException: Pool exhausted (50/50 active)
{t(29)} ERROR Payment failed for user_id=12345
    """.strip().split('\n')
    
    # Initialize preprocessor
    preprocessor = LogPreprocessor(
        lookback_minutes=5,
        root_service="payment-service"
    )
    
    # Add event
    preprocessor.add_event({
        "id": "evt_001",
        "type": "alert",
        "reason": "Error rate exceeded 5%",
        "service": "payment-service",
        "timestamp": "2026-01-28T16:55:30.000Z"
    })
    
    # Set metrics
    preprocessor.set_metrics({
        "cpuZ": 2.1,
        "memZ": 3.8,
        "latencyZ": 4.5,
        "errorRateZ": 6.2
    })
    
    # Process logs
    log_source = LogSource(
        type="application",
        file="/var/log/myapp/application.log",
        container="payment-service-7d4f8b-xkz2p",
        namespace="production"
    )
    
    bundle = preprocessor.process_lines(raw_logs, log_source)
    
    if bundle:
        import json
        print("=" * 60)
        print("CORRELATION BUNDLE OUTPUT")
        print("=" * 60)
        print(json.dumps(bundle, indent=2))
