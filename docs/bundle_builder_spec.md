# Bundle Builder Specification

> **For:** Go Developer building the Log Streaming Agent  
> **Version:** 1.0  
> **Last Updated:** 2026-01-29

---

## Overview

After a flush, the flushed logs must be transformed into a **CorrelationBundle** before sending to Opscure AI. This document specifies the bundle building logic.

```
┌─────────────────────────────────────────────────────────────────┐
│                     BUNDLE BUILDER FLOW                         │
│                                                                 │
│   Flushed Logs ──▶ Deduplicate ──▶ Build Bundle ──▶ Send API   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Input: Flushed Logs

After flush, you receive a slice of `ParsedLog`:

```go
type ParsedLog struct {
    Timestamp time.Time
    Level     string      // "ERROR" | "WARNING" | "INFO"
    Message   string      // Full message including stack traces
    LogSource LogSource
    RawLine   string
}

type LogSource struct {
    Type      string  // "application" | "system" | "access" | "gc"
    File      string  // "/var/log/myapp/app.log"
    Container string  // "payment-service-7d4f8b"
    Namespace string  // "production"
    Node      string  // "node-1"
}
```

---

## Step 1: Deduplicate Patterns

### Purpose

Reduce many similar logs into counted patterns. This:
- Reduces payload size
- Shows frequency of issues
- Helps AI identify recurring problems

### Normalization

Replace variable parts with placeholders before hashing:

```go
func normalizeMessage(msg string) string {
    result := msg
    
    // UUIDs: 550e8400-e29b-41d4-a716-446655440000 → <UUID>
    result = regexp.MustCompile(
        `\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b`,
    ).ReplaceAllString(result, "<UUID>")
    
    // IP addresses: 192.168.1.100 → <IP>
    result = regexp.MustCompile(
        `\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b`,
    ).ReplaceAllString(result, "<IP>")
    
    // Common IDs: user_id=12345 → id=<ID>
    result = regexp.MustCompile(
        `(?i)(user_?id|order_?id|request_?id|session_?id|id)[=:]\s*\w+`,
    ).ReplaceAllString(result, "id=<ID>")
    
    // Large numbers (6+ digits): 1234567890 → <NUM>
    // But preserve line numbers in stack traces
    result = regexp.MustCompile(
        `(?<![:(])\b\d{6,}\b(?!\))`,
    ).ReplaceAllString(result, "<NUM>")
    
    // Timestamps in message: 2026-01-28T16:52:00 → <TS>
    result = regexp.MustCompile(
        `\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}`,
    ).ReplaceAllString(result, "<TS>")
    
    return result
}
```

### Grouping Algorithm

```go
type LogPattern struct {
    Pattern         string    // Original message (first occurrence)
    Count           int       // How many times seen
    FirstOccurrence time.Time
    LastOccurrence  time.Time
    ErrorClass      string    // "ERROR" | "WARNING" | "INFO"
    LogSource       LogSource
}

func deduplicateLogs(logs []ParsedLog) []LogPattern {
    patterns := make(map[string]*LogPattern)
    
    for _, log := range logs {
        // Create hash key from normalized message
        normalized := normalizeMessage(log.Message)
        key := md5Hash(normalized)
        
        if p, exists := patterns[key]; exists {
            // Update existing pattern
            p.Count++
            p.LastOccurrence = log.Timestamp
            // Escalate level if needed (ERROR > WARNING > INFO)
            if log.Level == "ERROR" {
                p.ErrorClass = "ERROR"
            }
        } else {
            // Create new pattern
            patterns[key] = &LogPattern{
                Pattern:         log.Message,  // Keep ORIGINAL, not normalized
                Count:           1,
                FirstOccurrence: log.Timestamp,
                LastOccurrence:  log.Timestamp,
                ErrorClass:      log.Level,
                LogSource:       log.LogSource,
            }
        }
    }
    
    // Convert to slice and sort by severity
    result := make([]LogPattern, 0, len(patterns))
    for _, p := range patterns {
        result = append(result, *p)
    }
    
    // Sort: ERROR first, then WARNING, then INFO
    // Within same level, sort by count (descending)
    sort.Slice(result, func(i, j int) bool {
        severityOrder := map[string]int{"ERROR": 0, "WARNING": 1, "INFO": 2}
        if severityOrder[result[i].ErrorClass] != severityOrder[result[j].ErrorClass] {
            return severityOrder[result[i].ErrorClass] < severityOrder[result[j].ErrorClass]
        }
        return result[i].Count > result[j].Count
    })
    
    return result
}

func md5Hash(s string) string {
    h := md5.Sum([]byte(s))
    return hex.EncodeToString(h[:])
}
```

---

## Step 2: Extract Affected Services

Extract unique service names from log sources:

```go
func extractAffectedServices(patterns []LogPattern) []string {
    services := make(map[string]bool)
    
    for _, p := range patterns {
        if p.LogSource.Container != "" {
            // Clean K8s pod name → service name
            // "payment-service-7d4f8b-xyz12" → "payment-service"
            svc := cleanPodName(p.LogSource.Container)
            services[svc] = true
        }
    }
    
    result := make([]string, 0, len(services))
    for svc := range services {
        result = append(result, svc)
    }
    return result
}

func cleanPodName(podName string) string {
    // Remove K8s suffixes: -7d4f8b-xyz12, -abc123
    result := podName
    
    // Remove random hash suffix: -[a-f0-9]+-[a-z0-9]+$
    result = regexp.MustCompile(`-[a-f0-9]+-[a-z0-9]+$`).ReplaceAllString(result, "")
    
    // Remove replica number: -\d+$
    result = regexp.MustCompile(`-\d+$`).ReplaceAllString(result, "")
    
    return result
}
```

---

## Step 3: Build CorrelationBundle

### Data Structures

```go
type CorrelationBundle struct {
    Bundle  BundleData `json:"bundle"`
    UseRAG  bool       `json:"use_rag"`
    TopK    int        `json:"top_k"`
}

type BundleData struct {
    ID               string              `json:"id"`
    WindowStart      string              `json:"windowStart"`      // ISO 8601
    WindowEnd        string              `json:"windowEnd"`        // ISO 8601
    RootService      string              `json:"rootService"`
    AffectedServices []string            `json:"affectedServices"`
    LogPatterns      []LogPatternJSON    `json:"logPatterns"`
    Events           []Event             `json:"events"`
    Metrics          *Metrics            `json:"metrics"`
    GitConfig        *GitConfig          `json:"git_config"`
    FlushMetadata    *FlushMetadata      `json:"flush_metadata,omitempty"`
}

type LogPatternJSON struct {
    Pattern         string         `json:"pattern"`
    Count           int            `json:"count"`
    FirstOccurrence string         `json:"firstOccurrence"`  // ISO 8601
    LastOccurrence  string         `json:"lastOccurrence"`   // ISO 8601
    ErrorClass      string         `json:"errorClass"`
    LogSource       LogSourceJSON  `json:"logSource"`
}

type LogSourceJSON struct {
    Type      string `json:"type,omitempty"`
    File      string `json:"file,omitempty"`
    Container string `json:"container,omitempty"`
    Namespace string `json:"namespace,omitempty"`
    Node      string `json:"node,omitempty"`
}

type Event struct {
    ID        string `json:"id"`
    Type      string `json:"type"`      // "alert" | "deployment" | "scale"
    Reason    string `json:"reason"`
    Service   string `json:"service"`
    Timestamp string `json:"timestamp"` // ISO 8601
}

type Metrics struct {
    CPUZ       *float64 `json:"cpuZ"`
    MemZ       *float64 `json:"memZ"`
    LatencyZ   *float64 `json:"latencyZ"`
    ErrorRateZ *float64 `json:"errorRateZ"`
}

type GitConfig struct {
    UserName  string `json:"user_name"`
    UserEmail string `json:"user_email"`
}

type FlushMetadata struct {
    Reason    string `json:"reason"`     // Flush trigger
    LogCount  int    `json:"log_count"`
    FlushedAt string `json:"flushed_at"` // ISO 8601
}
```

### Builder Function

```go
func BuildCorrelationBundle(
    logs []ParsedLog,
    flushReason FlushReason,
    rootService string,
    events []Event,
    metrics *Metrics,
    gitConfig *GitConfig,
) CorrelationBundle {
    
    // 1. Deduplicate logs into patterns
    patterns := deduplicateLogs(logs)
    
    // 2. Calculate time window
    windowStart, windowEnd := calculateTimeWindow(patterns)
    
    // 3. Extract affected services
    affectedServices := extractAffectedServices(patterns)
    
    // 4. Convert patterns to JSON format
    patternJSON := make([]LogPatternJSON, len(patterns))
    for i, p := range patterns {
        patternJSON[i] = LogPatternJSON{
            Pattern:         p.Pattern,
            Count:           p.Count,
            FirstOccurrence: p.FirstOccurrence.Format(time.RFC3339),
            LastOccurrence:  p.LastOccurrence.Format(time.RFC3339),
            ErrorClass:      p.ErrorClass,
            LogSource: LogSourceJSON{
                Type:      p.LogSource.Type,
                File:      p.LogSource.File,
                Container: p.LogSource.Container,
                Namespace: p.LogSource.Namespace,
                Node:      p.LogSource.Node,
            },
        }
    }
    
    // 5. Generate bundle ID
    bundleID := generateBundleID()
    
    // 6. Assemble bundle
    return CorrelationBundle{
        Bundle: BundleData{
            ID:               bundleID,
            WindowStart:      windowStart,
            WindowEnd:        windowEnd,
            RootService:      rootService,
            AffectedServices: affectedServices,
            LogPatterns:      patternJSON,
            Events:           events,
            Metrics:          metrics,
            GitConfig:        gitConfig,
            FlushMetadata: &FlushMetadata{
                Reason:    string(flushReason),
                LogCount:  len(logs),
                FlushedAt: time.Now().Format(time.RFC3339),
            },
        },
        UseRAG: true,
        TopK:   5,
    }
}

func calculateTimeWindow(patterns []LogPattern) (string, string) {
    if len(patterns) == 0 {
        now := time.Now().Format(time.RFC3339)
        return now, now
    }
    
    var earliest, latest time.Time
    for i, p := range patterns {
        if i == 0 {
            earliest = p.FirstOccurrence
            latest = p.LastOccurrence
        } else {
            if p.FirstOccurrence.Before(earliest) {
                earliest = p.FirstOccurrence
            }
            if p.LastOccurrence.After(latest) {
                latest = p.LastOccurrence
            }
        }
    }
    
    return earliest.Format(time.RFC3339), latest.Format(time.RFC3339)
}

func generateBundleID() string {
    now := time.Now()
    randomSuffix := make([]byte, 4)
    rand.Read(randomSuffix)
    return fmt.Sprintf("incident_%s_%x", 
        now.Format("20060102_150405"), 
        randomSuffix)
}
```

---

## Step 4: Send to Opscure API

```go
func SendBundle(bundle CorrelationBundle, apiURL, apiKey string) error {
    jsonData, err := json.Marshal(bundle)
    if err != nil {
        return fmt.Errorf("failed to marshal bundle: %w", err)
    }
    
    req, err := http.NewRequest("POST", apiURL+"/analyze", bytes.NewBuffer(jsonData))
    if err != nil {
        return fmt.Errorf("failed to create request: %w", err)
    }
    
    req.Header.Set("Content-Type", "application/json")
    req.Header.Set("Authorization", "Bearer "+apiKey)
    
    client := &http.Client{Timeout: 30 * time.Second}
    resp, err := client.Do(req)
    if err != nil {
        return fmt.Errorf("failed to send request: %w", err)
    }
    defer resp.Body.Close()
    
    if resp.StatusCode != http.StatusOK {
        body, _ := io.ReadAll(resp.Body)
        return fmt.Errorf("API error %d: %s", resp.StatusCode, string(body))
    }
    
    return nil
}
```

---

## Complete Integration

```go
// In your flush callback:
func onFlush(logs []ParsedLog, reason FlushReason) {
    // Build bundle
    bundle := BuildCorrelationBundle(
        logs,
        reason,
        "payment-service",  // Root service
        pendingEvents,      // External events
        currentMetrics,     // Current metrics
        &GitConfig{
            UserName:  "ops-bot",
            UserEmail: "ops@company.com",
        },
    )
    
    // Send to Opscure
    if err := SendBundle(bundle, "https://opscure-api.example.com", apiKey); err != nil {
        log.Printf("Failed to send bundle: %v", err)
        // Implement retry logic here
    }
    
    // Clear pending events after successful send
    pendingEvents = nil
}
```

---

## Example Output

```json
{
  "bundle": {
    "id": "incident_20260128_165300_a1b2c3d4",
    "windowStart": "2026-01-28T16:52:00Z",
    "windowEnd": "2026-01-28T16:53:00Z",
    "rootService": "payment-service",
    "affectedServices": ["payment-service", "user-service"],
    
    "logPatterns": [
      {
        "pattern": "java.sql.SQLException: Cannot acquire connection from pool\n    at com.zaxxer.hikari.pool.HikariPool.getConnection(HikariPool.java:89)\n    at com.example.PaymentService.process(PaymentService.java:67)",
        "count": 5,
        "firstOccurrence": "2026-01-28T16:52:45Z",
        "lastOccurrence": "2026-01-28T16:53:00Z",
        "errorClass": "ERROR",
        "logSource": {
          "type": "application",
          "container": "payment-service-7d4f8b",
          "namespace": "production"
        }
      },
      {
        "pattern": "HikariPool-1 - Connection pool approaching limit: <NUM>/50 active",
        "count": 12,
        "firstOccurrence": "2026-01-28T16:52:00Z",
        "lastOccurrence": "2026-01-28T16:52:50Z",
        "errorClass": "WARNING",
        "logSource": {
          "type": "application",
          "container": "payment-service-7d4f8b",
          "namespace": "production"
        }
      }
    ],
    
    "events": [
      {
        "id": "evt_001",
        "type": "alert",
        "reason": "Error rate exceeded 5%",
        "service": "payment-service",
        "timestamp": "2026-01-28T16:55:30Z"
      }
    ],
    
    "metrics": {
      "cpuZ": 2.1,
      "memZ": 3.8,
      "latencyZ": 4.5,
      "errorRateZ": 6.2
    },
    
    "git_config": {
      "user_name": "ops-bot",
      "user_email": "ops@company.com"
    },
    
    "flush_metadata": {
      "reason": "error_detected",
      "log_count": 17,
      "flushed_at": "2026-01-28T16:53:01Z"
    }
  },
  "use_rag": true,
  "top_k": 5
}
```

---

## Testing Checklist

### Deduplication
- [ ] Similar messages grouped correctly
- [ ] Count increments for duplicates
- [ ] First/last occurrence tracked
- [ ] Original message preserved (not normalized)
- [ ] Patterns sorted by severity then count

### Normalization
- [ ] UUIDs replaced with `<UUID>`
- [ ] IP addresses replaced with `<IP>`
- [ ] IDs replaced with `id=<ID>`
- [ ] Large numbers replaced with `<NUM>`
- [ ] Stack trace line numbers preserved

### Bundle Building
- [ ] Bundle ID unique
- [ ] Time window calculated correctly
- [ ] Affected services extracted from containers
- [ ] All fields serialized correctly to JSON
- [ ] Flush metadata included

### API Integration
- [ ] Request sent with correct headers
- [ ] JSON payload valid
- [ ] Error handling for failed requests
- [ ] Timeout configured

---

## Questions?

Contact the Opscure team or refer to:
- `docs/log_stream_flush_spec.md` - Flush trigger specification
- `src/ingestion/log_preprocessor.py` - Python reference implementation
