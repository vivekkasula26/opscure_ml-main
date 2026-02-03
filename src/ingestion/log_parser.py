"""
Log Ingestion Service for Opscure

Transforms raw text logs into structured CorrelationBundle objects.
Handles timestamp parsing, pattern deduction, and severity extraction.
"""

import re
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass, field

from src.common.types import CorrelationBundle, LogPattern, CodeSnippet, Metrics


@dataclass
class ParsedLogLine:
    """Intermediate representation of a parsed log line"""
    raw: str
    timestamp: Optional[str] = None
    severity: Optional[str] = None
    normalized_pattern: str = ""
    source_file: Optional[str] = None
    source_line: Optional[int] = None


class LogParserService:
    """
    Parses raw log streams into CorrelationBundle objects.
    
    Features:
    - Multi-format timestamp extraction
    - Pattern normalization (deduplication)
    - Severity/Error class detection
    - Code snippet extraction from stack traces
    """
    
    # Timestamp regex patterns (ordered by specificity)
    TIMESTAMP_PATTERNS = [
        # ISO-8601 with timezone: 2026-01-19T07:43:10.201Z
        (r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?)', '%Y-%m-%dT%H:%M:%S.%f'),
        # Spring Boot style: 2026-01-19 13:13:10.195
        (r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)', '%Y-%m-%d %H:%M:%S.%f'),
        # Common Log Format: 19/Jan/2026:13:55:36
        (r'(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})', '%d/%b/%Y:%H:%M:%S'),
    ]
    
    # Severity keywords (ordered by priority)
    SEVERITY_KEYWORDS = {
        'FATAL': 100,
        'PANIC': 100,
        'CRITICAL': 100,
        'EMERG': 100,
        'ERROR': 80,
        'EXCEPTION': 80,
        'FAIL': 80,
        'CRASH': 80,
        'WARN': 50,
        'WARNING': 50,
        'INFO': 20,
        'DEBUG': 10,
        'TRACE': 5,
    }
    
    # Normalization patterns
    NORMALIZATION_RULES = [
        # UUIDs
        (r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '<UUID>'),
        # Hex IDs (like commit hashes)
        (r'\b[a-f0-9]{7,40}\b', '<HEX>'),
        # IP Addresses
        (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>'),
        # Ports
        (r':\d{2,5}\b', ':<PORT>'),
        # Numbers (but preserve severity levels like 404, 500)
        (r'\b(?!404|500|503|200|201|301|302)\d+\b', '<NUM>'),
        # Memory addresses
        (r'0x[a-f0-9]+', '<ADDR>'),
        # Thread names like [exec-1], [housekeeper]
        (r'\[[^\]]*-\d+\]', '[<THREAD>]'),
    ]
    
    # Stack trace file pattern
    STACK_TRACE_PATTERN = re.compile(
        r'at\s+([\w.$]+)\.([\w$]+)\(([\w.]+):(\d+)\)'
    )
    
    def __init__(self, repo_root: Optional[str] = None):
        """
        Initialize the parser.
        
        Args:
            repo_root: Optional path to the git repo root for code snippet extraction
        """
        self.repo_root = repo_root
    
    def parse_stream(
        self, 
        raw_logs: str,
        service_name: Optional[str] = None
    ) -> CorrelationBundle:
        """
        Parse a raw log stream into a CorrelationBundle.
        
        Args:
            raw_logs: Multi-line string of raw logs
            service_name: Optional service name to set as rootService
            
        Returns:
            CorrelationBundle ready for AI analysis
        """
        lines = raw_logs.strip().splitlines()
        
        # Phase 1: Parse each line
        parsed_lines: List[ParsedLogLine] = []
        for line in lines:
            if line.strip():
                parsed = self._parse_line(line)
                parsed_lines.append(parsed)
        
        # Phase 2: Aggregate into patterns
        patterns = self._aggregate_patterns(parsed_lines)
        
        # Phase 3: Extract code snippets
        code_snippets = self._extract_code_snippets(parsed_lines)
        
        # Phase 4: Calculate time window
        timestamps = [p.timestamp for p in parsed_lines if p.timestamp]
        window_start = min(timestamps) if timestamps else datetime.utcnow().isoformat() + "Z"
        window_end = max(timestamps) if timestamps else datetime.utcnow().isoformat() + "Z"
        
        # Phase 5: Calculate error rate metric
        error_count = sum(1 for p in parsed_lines if p.severity in ['ERROR', 'FATAL', 'EXCEPTION'])
        total_count = len(parsed_lines)
        error_rate_z = (error_count / total_count * 10) if total_count > 0 else 0.0
        
        return CorrelationBundle(
            windowStart=window_start,
            windowEnd=window_end,
            rootService=service_name or self._infer_service_name(parsed_lines),
            affectedServices=[service_name] if service_name else [],
            logPatterns=patterns,
            events=[],
            metrics=Metrics(errorRateZ=round(error_rate_z, 2)),
            sequence=[],
            code_snippets=code_snippets,
            derivedRootCauseHint=self._derive_hint(patterns)
        )
    
    def _parse_line(self, line: str) -> ParsedLogLine:
        """Parse a single log line"""
        parsed = ParsedLogLine(raw=line)
        
        # Extract timestamp
        parsed.timestamp = self._extract_timestamp(line)
        
        # Extract severity
        parsed.severity = self._extract_severity(line)
        
        # Normalize pattern
        parsed.normalized_pattern = self._normalize(line)
        
        # Extract source file reference
        file_info = self._extract_file_reference(line)
        if file_info:
            parsed.source_file, parsed.source_line = file_info
        
        return parsed
    
    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from a log line"""
        for pattern, fmt in self.TIMESTAMP_PATTERNS:
            match = re.search(pattern, line)
            if match:
                ts_str = match.group(1)
                # Normalize to ISO format
                if ts_str.endswith('Z'):
                    return ts_str
                try:
                    # Handle microseconds exceeding 6 digits
                    if '.' in ts_str:
                        base, micro = ts_str.rsplit('.', 1)
                        micro = micro[:6].ljust(6, '0')
                        ts_str = f"{base}.{micro}"
                    dt = datetime.strptime(ts_str.replace('Z', ''), fmt.replace('Z', ''))
                    return dt.isoformat() + "Z"
                except ValueError:
                    continue
        return None
    
    def _extract_severity(self, line: str) -> Optional[str]:
        """Extract severity level from a log line"""
        line_upper = line.upper()
        
        # Check for bracketed severity first: [ERROR], [WARN]
        bracket_match = re.search(r'\[(\w+)\]', line)
        if bracket_match:
            level = bracket_match.group(1).upper()
            if level in self.SEVERITY_KEYWORDS:
                return level
        
        # Fall back to keyword search
        for keyword in self.SEVERITY_KEYWORDS:
            if keyword in line_upper:
                return keyword
        
        return None
    
    def _normalize(self, line: str) -> str:
        """Normalize a log line into a pattern"""
        normalized = line
        
        # Remove timestamp (first part before the severity)
        for pattern, _ in self.TIMESTAMP_PATTERNS:
            normalized = re.sub(pattern, '', normalized)
        
        # Apply normalization rules
        for pattern, replacement in self.NORMALIZATION_RULES:
            normalized = re.sub(pattern, replacement, normalized)
        
        # Clean up whitespace
        normalized = ' '.join(normalized.split())
        
        return normalized.strip()
    
    def _extract_file_reference(self, line: str) -> Optional[Tuple[str, int]]:
        """Extract file and line number from stack traces"""
        match = self.STACK_TRACE_PATTERN.search(line)
        if match:
            file_name = match.group(3)
            line_num = int(match.group(4))
            return (file_name, line_num)
        return None
    
    def _aggregate_patterns(self, parsed_lines: List[ParsedLogLine]) -> List[LogPattern]:
        """Aggregate parsed lines into deduplicated patterns"""
        pattern_map: Dict[str, LogPattern] = {}
        
        for parsed in parsed_lines:
            key = parsed.normalized_pattern
            
            if key not in pattern_map:
                pattern_map[key] = LogPattern(
                    pattern=parsed.raw[:1000],  # Keep original for readability
                    count=1,
                    firstOccurrence=parsed.timestamp or "",
                    lastOccurrence=parsed.timestamp or "",
                    errorClass=parsed.severity
                )
            else:
                p = pattern_map[key]
                p.count += 1
                if parsed.timestamp:
                    if not p.lastOccurrence or parsed.timestamp > p.lastOccurrence:
                        p.lastOccurrence = parsed.timestamp
                    if not p.firstOccurrence or parsed.timestamp < p.firstOccurrence:
                        p.firstOccurrence = parsed.timestamp
        
        return list(pattern_map.values())
    
    def _extract_code_snippets(self, parsed_lines: List[ParsedLogLine]) -> List[CodeSnippet]:
        """Extract code snippets from referenced files"""
        if not self.repo_root:
            return []
        
        snippets: List[CodeSnippet] = []
        seen_files: set = set()
        
        for parsed in parsed_lines:
            if parsed.source_file and parsed.source_file not in seen_files:
                seen_files.add(parsed.source_file)
                
                # Try to find the file in the repo
                file_path = self._find_file(parsed.source_file)
                if file_path:
                    content = self._read_snippet(file_path, parsed.source_line or 1)
                    if content:
                        snippets.append(CodeSnippet(
                            file_path=file_path,
                            content=content,
                            start_line=max(1, (parsed.source_line or 1) - 5),
                            end_line=(parsed.source_line or 1) + 10
                        ))
        
        return snippets[:5]  # Limit to 5 snippets
    
    def _find_file(self, filename: str) -> Optional[str]:
        """Find a file in the repo by name"""
        if not self.repo_root:
            return None
        
        for root, _, files in os.walk(self.repo_root):
            if filename in files:
                return os.path.join(root, filename)
        return None
    
    def _read_snippet(self, file_path: str, center_line: int, context: int = 10) -> Optional[str]:
        """Read a code snippet from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            start = max(0, center_line - context - 1)
            end = min(len(lines), center_line + context)
            
            return ''.join(lines[start:end])
        except Exception:
            return None
    
    def _infer_service_name(self, parsed_lines: List[ParsedLogLine]) -> Optional[str]:
        """Try to infer the service name from log content"""
        for parsed in parsed_lines:
            # Look for common patterns like "com.beko.DemoBank"
            match = re.search(r'com\.(\w+)\.(\w+)', parsed.raw)
            if match:
                return match.group(2).lower()
        return None
    
    def _derive_hint(self, patterns: List[LogPattern]) -> Optional[str]:
        """Derive a root cause hint from the patterns"""
        # Count error types
        error_patterns = [p for p in patterns if p.errorClass in ['ERROR', 'FATAL', 'EXCEPTION']]
        
        if not error_patterns:
            return None
        
        # Find the most frequent error
        top_error = max(error_patterns, key=lambda p: p.count)
        
        # Simple pattern matching for common issues
        pattern_lower = top_error.pattern.lower()
        
        if '404' in pattern_lower or 'not found' in pattern_lower:
            return "HTTP 404 errors detected - possible missing endpoint or route"
        if 'connection' in pattern_lower and ('pool' in pattern_lower or 'exhaust' in pattern_lower):
            return "Database connection pool issues detected"
        if 'timeout' in pattern_lower:
            return "Timeout errors detected - possible performance or network issues"
        if 'memory' in pattern_lower or 'oom' in pattern_lower:
            return "Memory issues detected - possible memory leak or insufficient resources"
        
        return f"Primary error: {top_error.pattern[:100]}"


# Singleton instance
_parser_service: Optional[LogParserService] = None


def get_log_parser_service(repo_root: Optional[str] = None) -> LogParserService:
    """Get or create the log parser service singleton"""
    global _parser_service
    
    if _parser_service is None:
        _parser_service = LogParserService(repo_root=repo_root)
    
    return _parser_service
