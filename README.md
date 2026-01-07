# Opscure AI Pipeline

**CorrelationBundle → AIRecommendation Pipeline**

A focused AI service that takes correlated incident data and produces actionable recommendations using RAG and LLM inference.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CorrelationBundle (INPUT)                       │
│  • logPatterns, events, metrics, dependencyGraph, sequence             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                            SUMMARIZER                                    │
│  • Build textual summary for embedding                                  │
│  • Highlight: rootService, errorClasses, anomalies, events              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         PINECONE CLIENT (RAG)                           │
│  • Embed summary → vector                                               │
│  • Query similar historical incidents (top-5)                           │
│  • Return RetrievedIncident[] with past solutions                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          PROMPT BUILDER                                  │
│  • Combine CorrelationBundle + similar incidents                        │
│  • Format as structured prompt for LLM                                  │
│  • Include output JSON schema                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       OLLAMA CLIENT + FALLBACK                          │
│  • Try: gpt-oss → llama3.1:70b → mixtral                               │
│  • Retry logic with exponential backoff                                 │
│  • Return degraded response if all fail                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        AI OUTPUT PARSER                                  │
│  • Extract JSON from LLM response                                       │
│  • Validate required fields                                             │
│  • Fill defaults for missing fields                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       AIRecommendation (OUTPUT)                         │
│  • rootCause, causalChain, recommendedAction (FixPlan)                 │
│  • aiConfidence, autoHealCandidate                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
confidence-engine/
├── src/
│   ├── common/
│   │   ├── __init__.py
│   │   └── types.py              # CorrelationBundle, AIRecommendation, FixPlan
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── summarizer.py         # Bundle → text summary
│   │   ├── pinecone_client.py    # RAG retrieval
│   │   ├── prompt_builder.py     # Prompt construction
│   │   ├── ollama_client.py      # LLM inference with fallback
│   │   ├── ai_output_parser.py   # JSON parsing and validation
│   │   └── ai_adapter_service.py # Main orchestration
│   └── api/
│       ├── __init__.py
│       └── main.py               # FastAPI endpoints
├── requirements.txt
└── README.md
```

## Quick Start

### 1. Install Dependencies

```bash
cd confidence-engine
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Optional: Set API keys for full functionality
export OLLAMA_URL="http://localhost:11434"
export PINECONE_API_KEY="your-pinecone-key"
export OPENAI_API_KEY="your-openai-key"  # For embeddings
```

### 3. Start Ollama

```bash
# Install Ollama from https://ollama.ai
ollama pull llama3:8b
ollama serve
```

### 4. Run the API

```bash
uvicorn src.api.main:app --reload --port 8000
```

## API Endpoints

### Main Endpoint

```
POST /ai/analyze
```

**Request:**

```json
{
  "bundle": {
    "id": "corr_001",
    "windowStart": "2024-12-04T10:30:00Z",
    "windowEnd": "2024-12-04T10:35:00Z",
    "rootService": "database",
    "affectedServices": ["database", "api-gateway"],
    "logPatterns": [
      {
        "pattern": "Connection pool exhausted",
        "count": 47,
        "firstOccurrence": "2024-12-04T10:30:15Z",
        "lastOccurrence": "2024-12-04T10:34:58Z",
        "errorClass": "ConnectionPoolError"
      }
    ],
    "events": [
      {
        "id": "evt_001",
        "type": "Warning",
        "reason": "HighLatency",
        "service": "database",
        "timestamp": "2024-12-04T10:30:10Z"
      }
    ],
    "metrics": {
      "cpuZ": 2.8,
      "latencyZ": 4.2,
      "errorRateZ": 3.9
    },
    "dependencyGraph": ["database", "api-gateway", "frontend"],
    "derivedRootCauseHint": "Database connection pool exhaustion"
  },
  "use_rag": true,
  "top_k": 5
}
```

**Response:**

```json
{
  "recommendation": {
    "id": "rec_abc123",
    "correlationBundleId": "corr_001",
    "rootCause": "Database connection pool exhausted due to traffic spike",
    "causalChain": [
      "Traffic spike",
      "Connection pool exhaustion",
      "API gateway timeouts",
      "Frontend errors"
    ],
    "recommendedAction": {
      "action": "scale",
      "target": "database-pool",
      "parameters": {
        "max_connections": 50,
        "idle_timeout": "30s"
      }
    },
    "aiConfidence": 0.87,
    "autoHealCandidate": true
  },
  "latency_ms": 1234.56
}
```

### Other Endpoints

| Endpoint             | Method | Description                     |
| -------------------- | ------ | ------------------------------- |
| `/health`            | GET    | Health check                    |
| `/ready`             | GET    | Readiness with component health |
| `/ai/analyze`        | POST   | Full analysis with options      |
| `/ai/analyze/simple` | POST   | Takes just CorrelationBundle    |
| `/ai/analyze/no-rag` | POST   | Analyze without RAG             |
| `/ai/metrics`        | GET    | Service metrics                 |
| `/ai/example-bundle` | GET    | Get example bundle for testing  |

## Types

### CorrelationBundle (Input)

```typescript
CorrelationBundle {
  id: string
  windowStart: string          // ISO timestamp
  windowEnd: string            // ISO timestamp
  rootService?: string         // Suspected root cause service
  affectedServices: string[]   // All affected services

  logPatterns: {
    pattern: string
    count: number
    firstOccurrence: string
    lastOccurrence: string
    errorClass?: string
  }[]

  events: {
    id: string
    type: string               // Warning, Error, etc.
    reason: string
    pod?: string
    service?: string
    timestamp: string
  }[]

  metrics: {
    cpuZ?: number              // Z-score
    memZ?: number
    latencyZ?: number
    errorRateZ?: number
    anomalyVector?: number[]
  }

  dependencyGraph: string[]    // Service dependency chain

  sequence: {
    timestamp: string
    type: "log" | "event" | "metric"
    message: string
    sequenceIndex: number
  }[]

  derivedRootCauseHint?: string
}
```

### AIRecommendation (Output)

```typescript
AIRecommendation {
  id: string
  correlationBundleId: string
  rootCause: string
  causalChain: string[]
  recommendedAction: {
    action: string             // restart, scale, patch, rollback, etc.
    target: string             // Service/deployment name
    parameters?: Record<string, any>
  }
  aiConfidence: number         // 0.0 - 1.0
  autoHealCandidate: boolean   // Safe for automated execution?
  rawModelOutput?: any         // For debugging
}
```

## Components

### 1. Summarizer (`src/ai/summarizer.py`)

Builds concise text from CorrelationBundle for embedding:

- Highlights root service and affected services
- Extracts error classes from log patterns
- Summarizes metric anomalies (Z-scores > 2.0)
- Includes key events and dependency chain

### 2. PineconeClient (`src/ai/pinecone_client.py`)

RAG retrieval for similar incidents:

- Creates embeddings (OpenAI or mock fallback)
- Queries Pinecone for top-K similar incidents
- Returns historical solutions for context

### 3. PromptBuilder (`src/ai/prompt_builder.py`)

Constructs structured prompts:

- System prompt: SRE expert instructions
- User prompt: Bundle JSON + similar incidents + output schema
- Ensures LLM returns valid JSON

### 4. OllamaClient (`src/ai/ollama_client.py`)

LLM inference with fallback:

- Primary: `gpt-oss` (2 retries)
- Fallback 1: `llama3.1:70b` (1 attempt)
- Fallback 2: `mixtral` (1 attempt)
- Degraded response if all fail

### 5. AIOutputParser (`src/ai/ai_output_parser.py`)

Safe JSON parsing:

- Extracts JSON from markdown blocks
- Validates required fields
- Fills defaults for missing fields
- Returns degraded recommendation on error

### 6. AIAdapterService (`src/ai/ai_adapter_service.py`)

Main orchestrator:

- Coordinates all components
- Tracks metrics (requests, latency, success rate)
- Provides health check

## Testing

```bash
# Get example bundle
curl http://localhost:8000/ai/example-bundle > bundle.json

# Analyze bundle
curl -X POST http://localhost:8000/ai/analyze \
  -H "Content-Type: application/json" \
  -d @bundle.json

# Check health
curl http://localhost:8000/ready
```

## Fallback Behavior

When Ollama models fail, the system returns a degraded response:

```json
{
  "rootCause": "unknown",
  "causalChain": [],
  "autoHealCandidate": false,
  "recommendedAction": {
    "action": "none",
    "target": ""
  },
  "aiConfidence": 0.0
}
```

This ensures the API always returns valid data, even during outages.
