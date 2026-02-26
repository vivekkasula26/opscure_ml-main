# Log Stream Flush Specification

> **For:** Go Developer building the Log Streaming Agent  
> **Version:** 1.0  
> **Last Updated:** 2026-01-29

---

## Overview

The Log Streaming Agent captures raw logs and flushes them to Opscure AI for analysis. This document specifies the **buffer and flush logic** that must be implemented.

```
┌─────────────────────────────────────────────────────────────────┐
│                        LOG STREAM FLOW                          │
│                                                                 │
│   Raw Logs ──▶ [60s Buffer] ──▶ ERROR? ──▶ FLUSH ──▶ Bundle    │
│                     │                         │                 │
│                     │                         ▼                 │
│               Prune > 60s              Send to Opscure          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Concepts

### 1. Sliding Window Buffer (60 seconds)

- Maintain a **ring buffer** of parsed logs
- Only keep logs from the **last 60 seconds**
- Logs older than 60 seconds are **pruned** (discarded)

### 2. Flush Triggers

There are **4 flush triggers** that cause the buffer to flush:

| Trigger | Description | Priority |
|---------|-------------|----------|
| `ERROR_DETECTED` | Immediate flush when ERROR-level log arrives | **Highest** |
| `TIME_ELAPSED` | Periodic flush every `flush_interval_seconds` | Medium |
| `MANUAL` | Explicit `Flush()` call from application | Low |
| `SHUTDOWN` | Graceful shutdown signal (context cancellation) | **Critical** |

### 3. Configuration

```go
type FlushConfig struct {
    WindowSeconds          int   // 60 - sliding window size
    FlushIntervalSeconds   int   // 30 - periodic flush interval
    ErrorTriggersImmediate bool  // true - ERROR = instant flush
}

// Recommended defaults
var DefaultConfig = FlushConfig{
    WindowSeconds:          60,
    FlushIntervalSeconds:   30,
    ErrorTriggersImmediate: true,
}
```

### 4. Post-Flush State

- Buffer is **cleared** after flush
- New logs start accumulating in fresh buffer
- Ready for next incident
- Flush reason is included in bundle metadata

---

## Data Structures

### ParsedLog

Each log entry after parsing:

```go
type ParsedLog struct {
    Timestamp time.Time   // When the log occurred
    Level     string      // "ERROR" | "WARNING" | "INFO"
    Message   string      // Full message (including stack traces)
    LogSource LogSource   // Source metadata
    RawLine   string      // Original raw line
}

type LogSource struct {
    Type      string // "application" | "system" | "access" | "gc"
    File      string // e.g., "/var/log/myapp/app.log"
    Container string // e.g., "payment-service-7d4f8b"
    Namespace string // e.g., "production"
    Node      string // e.g., "node-1"
}
```

### LogPattern (after deduplication)

```go
type LogPattern struct {
    Pattern         string    // Representative log message
    Count           int       // How many times this pattern occurred
    FirstOccurrence time.Time // First time seen in window
    LastOccurrence  time.Time // Last time seen in window
    ErrorClass      string    // "ERROR" | "WARNING" | "INFO"
    LogSource       LogSource // Source metadata
}
```

---

## Buffer Implementation

### FlushReason Enum

```go
type FlushReason string

const (
    FlushErrorDetected FlushReason = "error_detected"  // ERROR log arrived
    FlushTimeElapsed   FlushReason = "time_elapsed"    // Periodic interval
    FlushManual        FlushReason = "manual"          // Explicit Flush() call
    FlushShutdown      FlushReason = "shutdown"        // Graceful shutdown
)
```

### Complete Implementation

```go
type LogBuffer struct {
    config        FlushConfig
    buffer        []ParsedLog
    mu            sync.RWMutex
    
    lastFlushTime time.Time  // For periodic flush
    
    onFlush       func([]ParsedLog, FlushReason)  // Callback
    
    ctx           context.Context   // For shutdown
    cancel        context.CancelFunc
}

func NewLogBuffer(config FlushConfig, onFlush func([]ParsedLog, FlushReason)) *LogBuffer {
    ctx, cancel := context.WithCancel(context.Background())
    
    b := &LogBuffer{
        config:        config,
        buffer:        make([]ParsedLog, 0),
        lastFlushTime: time.Now(),
        onFlush:       onFlush,
        ctx:           ctx,
        cancel:        cancel,
    }
    
    // Start background flush goroutine
    go b.backgroundFlushLoop()
    
    return b
}

// Add adds a log and checks immediate flush conditions
func (b *LogBuffer) Add(log ParsedLog) FlushReason {
    b.mu.Lock()
    defer b.mu.Unlock()
    
    // 1. Prune logs older than window
    b.pruneOld()
    
    // 2. Add new log
    b.buffer = append(b.buffer, log)
    
    // 3. ERROR_DETECTED - immediate flush
    if b.config.ErrorTriggersImmediate && log.Level == "ERROR" {
        b.executeFlush(FlushErrorDetected)
        return FlushErrorDetected
    }
    
    return "" // No flush
}

// Flush manually triggers a flush
func (b *LogBuffer) Flush() bool {
    b.mu.Lock()
    defer b.mu.Unlock()
    
    if len(b.buffer) > 0 {
        b.executeFlush(FlushManual)
        return true
    }
    return false
}

// Shutdown gracefully stops the buffer and flushes remaining logs
func (b *LogBuffer) Shutdown() {
    b.cancel() // Stop background goroutine
    
    b.mu.Lock()
    defer b.mu.Unlock()
    
    if len(b.buffer) > 0 {
        b.executeFlush(FlushShutdown)
    }
}

// backgroundFlushLoop checks TIME_ELAPSED
func (b *LogBuffer) backgroundFlushLoop() {
    ticker := time.NewTicker(1 * time.Second)
    defer ticker.Stop()
    
    for {
        select {
        case <-b.ctx.Done():
            return // Shutdown
        case <-ticker.C:
            b.checkScheduledFlush()
        }
    }
}

func (b *LogBuffer) checkScheduledFlush() {
    b.mu.Lock()
    defer b.mu.Unlock()
    
    if len(b.buffer) == 0 {
        return
    }
    
    // TIME_ELAPSED - periodic flush
    if time.Since(b.lastFlushTime).Seconds() >= float64(b.config.FlushIntervalSeconds) {
        b.executeFlush(FlushTimeElapsed)
    }
}

func (b *LogBuffer) pruneOld() {
    cutoff := time.Now().Add(-time.Duration(b.config.WindowSeconds) * time.Second)
    for len(b.buffer) > 0 && b.buffer[0].Timestamp.Before(cutoff) {
        b.buffer = b.buffer[1:]
    }
}

func (b *LogBuffer) executeFlush(reason FlushReason) {
    if len(b.buffer) == 0 {
        return
    }
    
    // Copy logs
    logs := make([]ParsedLog, len(b.buffer))
    copy(logs, b.buffer)
    
    // Clear buffer
    b.buffer = b.buffer[:0]
    b.lastFlushTime = time.Now()
    
    // Callback
    if b.onFlush != nil {
        b.onFlush(logs, reason)
    }
}
```

### Flush Trigger Summary

| Trigger | Where Checked | Condition |
|---------|---------------|-----------|
| `ERROR_DETECTED` | `Add()` | `log.Level == "ERROR"` |
| `TIME_ELAPSED` | Background goroutine | `time.Since(lastFlushTime) >= FlushIntervalSeconds` |
| `MANUAL` | `Flush()` | Explicit call |
| `SHUTDOWN` | `Shutdown()` | Context cancelled |

---

## Flush Flow

```
BEFORE FLUSH:
┌────────────────────────────────────────────────────────────┐
│ Buffer (60s window):                                       │
│ [INFO 16:52:00] [INFO 16:52:30] [WARN 16:52:45] [ERROR 16:53:00]
└────────────────────────────────────────────────────────────┘
                                                    │
                                             ERROR detected!
                                                    │
                                                    ▼
                                              FLUSH ALL
                                                    │
                                                    ▼
┌────────────────────────────────────────────────────────────┐
│ Output: All 4 logs → Deduplicate → CorrelationBundle       │
└────────────────────────────────────────────────────────────┘

AFTER FLUSH:
┌────────────────────────────────────────────────────────────┐
│ Buffer: [ empty ]                                          │
│ Ready for new logs                                         │
└────────────────────────────────────────────────────────────┘
```

---

## Log Parsing Rules

### 1. Timestamp Extraction

Support these formats:
```
2026-01-28T16:52:00.123Z          → ISO 8601
2026-01-28 16:52:00.123           → Space-separated
[2026-01-28T16:52:00]             → Bracketed
```

Regex patterns:
```regex
^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}
^\[\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}
```

### 2. Level Extraction

```go
func ExtractLevel(line string) string {
    upper := strings.ToUpper(line)
    
    if containsAny(upper, "ERROR", "FATAL", "CRITICAL", "EXCEPTION") {
        return "ERROR"
    }
    if containsAny(upper, "WARN", "WARNING") {
        return "WARNING"
    }
    return "INFO"
}
```

### 3. Stack Trace Grouping

**Multi-line stack traces must be grouped with their parent log entry.**

Stack trace continuation patterns:
```regex
^\s+at\s+              // Java: "    at com.example.Class.method"
^\s+File\s+"           // Python: '  File "/path", line 10'
^\s+\.\.\.\s+\d+       // Java: "    ... 15 more"
^Caused\s+by:          // Exception chains
```

**Logic:**
```go
for _, line := range rawLines {
    if isNewLogEntry(line) {           // Has timestamp
        saveCurrentEntry()
        startNewEntry(line)
    } else if isStackContinuation(line) {
        appendToCurrentEntry(line)     // Append to message
    }
}
```

---

## Deduplication (Post-Flush)

After flush, deduplicate logs before sending:

### Normalization

Replace variable parts with placeholders:
```
Original: "Connection timeout for user_id=12345"
Normalized: "Connection timeout for user_id=<ID>"

Original: "Request 550e8400-e29b-41d4-a716-446655440000 failed"  
Normalized: "Request <UUID> failed"
```

Patterns to normalize:
| Type | Regex | Replacement |
|------|-------|-------------|
| UUID | `[0-9a-f]{8}-[0-9a-f]{4}-...-[0-9a-f]{12}` | `<UUID>` |
| IP | `\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}` | `<IP>` |
| IDs | `(user_?id\|order_?id\|...)=\w+` | `id=<ID>` |
| Large Numbers | `\d{6,}` | `<NUM>` |
| Timestamps | `\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}` | `<TS>` |

### Grouping

```go
patterns := make(map[string]*LogPattern)

for _, log := range flushedLogs {
    normalized := normalize(log.Message)
    key := md5(normalized)
    
    if p, exists := patterns[key]; exists {
        p.Count++
        p.LastOccurrence = log.Timestamp
    } else {
        patterns[key] = &LogPattern{
            Pattern:         log.Message,  // Keep original
            Count:           1,
            FirstOccurrence: log.Timestamp,
            LastOccurrence:  log.Timestamp,
            ErrorClass:      log.Level,
            LogSource:       log.LogSource,
        }
    }
}
```

---

## Output: CorrelationBundle

After flush and deduplication, send this JSON to Opscure:

```json
{
  "bundle": {
    "id": "incident_20260128_165300_a1b2c3d4",
    "windowStart": "2026-01-28T16:52:00.000Z",
    "windowEnd": "2026-01-28T16:53:00.000Z",
    "rootService": "payment-service",
    "affectedServices": ["payment-service", "user-service"],
    
    "logPatterns": [
      {
        "pattern": "java.sql.SQLException: Cannot acquire connection\n    at com.zaxxer.hikari...",
        "count": 5,
        "firstOccurrence": "2026-01-28T16:52:45.000Z",
        "lastOccurrence": "2026-01-28T16:53:00.000Z",
        "errorClass": "ERROR",
        "logSource": {
          "type": "application",
          "container": "payment-service-7d4f8b",
          "namespace": "production"
        }
      },
      {
        "pattern": "Connection pool approaching limit: <NUM>/50 active",
        "count": 12,
        "firstOccurrence": "2026-01-28T16:52:00.000Z",
        "lastOccurrence": "2026-01-28T16:52:50.000Z",
        "errorClass": "WARNING",
        "logSource": { ... }
      }
    ],
    
    "events": [],
    "metrics": null,
    "git_config": {
      "user_name": "ops-bot",
      "user_email": "ops@company.com"
    }
  },
  "use_rag": true,
  "top_k": 5
}
```

### API Endpoint

```
POST https://opscure-api.example.com/analyze
Content-Type: application/json
Authorization: Bearer <API_KEY>

Body: <CorrelationBundle JSON>
```

---

## Edge Cases

### 1. No ERROR in 60 seconds
- Logs accumulate and get pruned as they age past 60s
- No bundle is sent
- This is normal behavior

### 2. Multiple ERRORs in quick succession
- First ERROR triggers flush → bundle sent
- Buffer clears
- Second ERROR triggers another flush (may have fewer logs)
- Each ERROR = separate bundle

### 3. Stack trace spans multiple lines
- Must be grouped with parent log entry
- Check for `at`, `Caused by:`, indentation patterns

### 4. Empty buffer on ERROR
- Can happen if ERROR is first log after flush
- Still create bundle with just that ERROR log

---

## Testing Checklist

### Buffer & Pruning
- [ ] 60-second window correctly prunes old logs
- [ ] Buffer is empty after flush
- [ ] Thread-safe under concurrent log ingestion

### Flush Triggers
- [ ] `ERROR_DETECTED` - ERROR log triggers immediate flush
- [ ] `TIME_ELAPSED` - Periodic flush after `FlushIntervalSeconds`
- [ ] `MANUAL` - `Flush()` method works correctly
- [ ] `SHUTDOWN` - `Shutdown()` flushes remaining logs before exit

### Parsing
- [ ] Stack traces grouped correctly with parent log
- [ ] Timestamps extracted from all supported formats
- [ ] Log levels detected correctly (ERROR, WARNING, INFO)

### Deduplication
- [ ] Similar logs grouped into patterns
- [ ] Count, first/last occurrence tracked correctly
- [ ] Patterns sorted by severity

### Output
- [ ] CorrelationBundle JSON matches schema
- [ ] `flush_reason` included in bundle metadata
- [ ] API call succeeds with valid bundle

---

## Questions?

Contact the Opscure team or refer to:
- `src/ingestion/log_preprocessor.py` - Python reference implementation
- `docs/architecture_deep_dive.md` - System architecture
