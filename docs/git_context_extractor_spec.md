# Git Context Extractor — Go Implementation Spec

## Overview

Implement a Go package that extracts git repository context for integration with the Opscure log correlation system. This context enriches `CorrelationBundle` payloads with repository metadata, enabling the AI to perform precise code-level analysis.

---

## Architecture: Connect Once, Serve On-Demand

The extractor follows a **cache-first pattern** — the user connects to git once during initialization, and the context is cached for subsequent requests.

```
┌─────────────────────────────────────────────────────────────┐
│                     Git Context Service                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌──────────────┐      ┌──────────────┐      ┌───────────┐ │
│   │  Initialize  │─────▶│    Cache     │◀────▶│  Git CLI  │ │
│   │  (once)      │      │  (in-memory) │      │           │ │
│   └──────────────┘      └──────────────┘      └───────────┘ │
│          │                     ▲                            │
│          │                     │                            │
│          ▼                     │                            │
│   ┌──────────────┐      ┌──────────────┐                    │
│   │  Background  │─────▶│   Refresh    │                    │
│   │  Watcher     │      │   Trigger    │                    │
│   └──────────────┘      └──────────────┘                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌───────────────────────┐
              │  GetContext() API     │
              │  (returns cached ctx) │
              └───────────────────────┘
```

### Lifecycle

| Phase | Action | Frequency |
|-------|--------|-----------|
| **Initialize** | Clone repo (if remote) or validate path, extract full context, populate cache | Once at startup |
| **Refresh** | Re-extract context on file system events or polling interval | On change / every N seconds |
| **Serve** | Return cached `GitContextPayload` | On every `GetContext()` call |

### Go Interface

```go
type GitContextService interface {
    // Initialize connects to the repository and performs initial extraction.
    // Call this once at application startup.
    Initialize(repoPath string, opts InitOptions) error
    
    // GetContext returns the cached git context.
    // This is cheap — it reads from memory, not from git.
    GetContext() (*GitContextPayload, error)
    
    // Refresh forces a re-extraction and updates the cache.
    // Normally called automatically by the background watcher.
    Refresh() error
    
    // Close stops background watchers and cleans up resources.
    Close() error
}

type InitOptions struct {
    RepoURL        string        // Remote URL to clone (optional if local path)
    Branch         string        // Branch to track (default: default branch)
    RefreshInterval time.Duration // Polling interval (default: 30s, 0 = disabled)
    WatchFileSystem bool         // Use fsnotify for instant refresh (default: true)
}
```

### Cache Refresh Triggers

The cache should refresh automatically when:

1. **File system change** — Use `fsnotify` to watch `.git/` directory
2. **Polling interval** — Fallback for environments where fsnotify isn't reliable
3. **Manual trigger** — Explicit `Refresh()` call after git operations

```go
// Example: Watch for git changes
watcher, _ := fsnotify.NewWatcher()
watcher.Add(filepath.Join(repoPath, ".git", "HEAD"))
watcher.Add(filepath.Join(repoPath, ".git", "refs", "heads"))

for event := range watcher.Events {
    if event.Op&fsnotify.Write != 0 {
        service.Refresh()
    }
}
```

---

## Output Schema

The extractor must produce JSON matching this structure:

```json
{
  "git_context": {
    "repo_url": "https://github.com/company/checkout-service",
    "branch": "main",
    "recent_commits": [
      {
        "sha": "a1b2c3d",
        "message": "Update database pool settings",
        "author": "dev@company.com",
        "timestamp": "2026-02-02T22:40:00Z"
      }
    ],
    "changed_files": [
      "src/main/resources/application.yml",
      "src/main/java/com/checkout/DatabaseConfig.java"
    ],
    "diff": "diff --git a/application.yml\n-  maxPoolSize: 100\n+  maxPoolSize: 20"
  },
  "git_config": {
    "user_name": "ops-bot",
    "user_email": "ops@company.com"
  }
}
```

---

## Go Data Structures

```go
package gitcontext

import "time"

type Commit struct {
    SHA       string    `json:"sha"`
    Message   string    `json:"message"`
    Author    string    `json:"author"`
    Timestamp time.Time `json:"timestamp"`
}

type GitContext struct {
    RepoURL       string   `json:"repo_url"`
    Branch        string   `json:"branch"`
    RecentCommits []Commit `json:"recent_commits"`
    ChangedFiles  []string `json:"changed_files"`
    Diff          string   `json:"diff"`
}

type GitConfig struct {
    UserName  string `json:"user_name"`
    UserEmail string `json:"user_email"`
}

type GitContextPayload struct {
    GitContext GitContext `json:"git_context"`
    GitConfig  GitConfig  `json:"git_config"`
}
```

---

## Extraction Commands

| Field | Git Command | Notes |
|-------|-------------|-------|
| `repo_url` | `git config --get remote.origin.url` | May be empty if no remote |
| `branch` | `git branch --show-current` | Falls back to `git rev-parse --abbrev-ref HEAD` |
| `recent_commits` | `git log -n 5 --pretty=format:%h\|%s\|%ae\|%aI` | Parse pipe-delimited output |
| `changed_files` | `git diff-tree --no-commit-id --name-only -r HEAD` | Files from last commit |
| `diff` | `git show HEAD --format= --unified=3` | Unified diff of last commit |
| `user_name` | `git config user.name` | Local git identity |
| `user_email` | `git config user.email` | Local git identity |

---

## Implementation Requirements

### 1. Package Signature

```go
// Extract extracts git context from the repository at the given path.
// If repoPath is empty, uses current working directory.
func Extract(repoPath string) (*GitContextPayload, error)

// ExtractWithOptions provides fine-grained control over extraction.
func ExtractWithOptions(repoPath string, opts ExtractOptions) (*GitContextPayload, error)

type ExtractOptions struct {
    CommitLimit    int    // Number of recent commits (default: 5)
    DiffContext    int    // Lines of diff context (default: 3)
    IncludeDiff    bool   // Whether to include full diff (default: true)
    TargetCommit   string // Specific commit to analyze (default: HEAD)
}
```

### 2. Error Handling

Return typed errors for common failure cases:

```go
var (
    ErrNotARepository = errors.New("path is not a git repository")
    ErrNoCommits      = errors.New("repository has no commits")
    ErrGitNotFound    = errors.New("git executable not found")
)
```

### 3. Command Execution

- Use `os/exec` to invoke git commands
- Set `GIT_TERMINAL_PROMPT=0` to prevent interactive prompts
- Capture both stdout and stderr
- Timeout after 10 seconds per command

```go
func runGit(repoPath string, args ...string) (string, error) {
    ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
    defer cancel()
    
    cmd := exec.CommandContext(ctx, "git", args...)
    cmd.Dir = repoPath
    cmd.Env = append(os.Environ(), "GIT_TERMINAL_PROMPT=0")
    
    output, err := cmd.Output()
    if err != nil {
        return "", fmt.Errorf("git %s: %w", args[0], err)
    }
    return strings.TrimSpace(string(output)), nil
}
```

### 4. Timestamp Parsing

Git's `%aI` format produces ISO 8601 timestamps. Parse with:

```go
timestamp, err := time.Parse(time.RFC3339, rawTimestamp)
```

### 5. Diff Size Limits

> [!IMPORTANT]
> Truncate diffs exceeding **50KB** to prevent payload bloat. Append `\n... [truncated]` when truncating.

---

## Testing Requirements

1. **Unit tests** for each extraction function
2. **Integration test** against a real git repository
3. **Edge cases**:
   - Empty repository (no commits)
   - Detached HEAD state
   - No remote configured
   - Missing git config values

---

## Integration Notes

The Python side will receive this payload via the existing log agent communication channel. The `GitContext` will be attached to the `CorrelationBundle.metadata` field before AI analysis.

### Example Usage (Consumer Side)

```python
# In bundle_builder.py
def enrich_with_git_context(bundle: CorrelationBundle, git_payload: dict):
    bundle.metadata["git_context"] = git_payload.get("git_context", {})
    bundle.metadata["git_config"] = git_payload.get("git_config", {})
```

---

## Deliverables

1. `pkg/gitcontext/extractor.go` — Core extraction logic
2. `pkg/gitcontext/types.go` — Data structures
3. `pkg/gitcontext/extractor_test.go` — Unit tests
4. Update main agent to call `gitcontext.Extract()` and include in output payload
