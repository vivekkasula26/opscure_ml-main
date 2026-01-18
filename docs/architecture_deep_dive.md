# Opscure System Architecture Deep Dive

This document provides a component-level technical explanation of the Opscure engine.

## 1. Data Model (`src/common/types.py`)

The core currency of the system is the **`CorrelationBundle`**.
```python
@dataclass
class CorrelationBundle:
    id: str           # Unique incident ID
    logPatterns: List[LogPattern]
    events: List[K8sEvent]
    metrics: MetricsSnapshot
    git_context: Optional[GitContext]  # The "Bridge" to code
    code_snippets: List[CodeSnippet]   # Retrieved from Git
```
This bundle aggregates 3 dimensions of data:
1.  **Observability**: Logs, K8s Events, Prometheus Metrics.
2.  **Source Code**: Snippets fetched from GitHub linked to stack traces.
3.  **Context**: Service mappings, dependency graphs.

## 2. The AI Pipeline (`src/ai/`)

The `AIAdapterService` orchestrates the "Thinking" phase.

### A. Context Retrieval (RAG) (`pinecone_client.py`)
Before asking the LLM, the system asks **Pinecone**: "Have we seen this vector before?"
1.  `Summarizer` converts the Bundle into a text description.
2.  `PineconeClient` embeds this text.
3.  Top-K similar historical incidents are retrieved.

### B. Prompt Engineering (`prompt_builder.py`)
The prompt is constructed dynamically:
1.  **System Prompt**: Defines the persona (SRE Expert) and **Tools** (File Edit, XML Edit, Runtime Op).
2.  **User Prompt**:
    *   Current Bundle JSON
    *   Similar Incidents JSON (RAG Context)
    *   Instruction to return strict JSON matching `OUTPUT_SCHEMA`.

### C. Inference & Parsing (`ai_adapter_service.py`)
1.  Calls `Ollama` or `Groq` API.
2.  `AIOutputParser` validates the JSON against Pydantic models.
3.  Converts the JSON into an `AIRecommendation` object.
4.  **Action Mapping**:
    *   `fix_type="file_edit"` -> `ActionType.FILE_EDIT`
    *   `fix_type="xml_block_edit"` -> `ActionType.XML_EDIT`
    *   `fix_type="runtime_remediation"` -> `ActionType.RUNTIME_OP`

## 3. The Trusted Agent (`src/remediation/`)

The `RemediationAgent` is the "Actor". It never blindly trusts the AI.

### A. Confidence Engine (`confidence.py`)
Every proposal is scored based on:
1.  **AI Confidence**: How sure is the model? (0.0 - 1.0)
2.  **Historical Success**: Has this *exact* action worked before? (Feedback Loop)
3.  **Risk Profile**: Is it a read-only op vs a data deletion?

**The Gate**:
```python
if score >= 0.99:
    return SafetyLevel.SAFE (Auto-Execute)
else:
    return SafetyLevel.REQUIRE_APPROVAL (Human Loop)
```

### B. Safety Matrix (`safety.py`)
A static rules engine checks the operation against policies:
-   **Blocklist**: "Never run `rm -rf /`".
-   **Scope**: "Prod" requires higher clearance than "Dev".

### C. Safe Execution (`patcher.py` / `xml_patcher.py`)
Unlike generic agents that run `sed`, Opscure uses **Structure-Aware Patchers**.

#### CodePatcher
Ensures semantic validity for code:
1.  **Anchor Matching**: Finds the `original_context` block.
2.  **Ambiguity Check**: Fails if the block appears multiple times.
3.  **Drift Check**: Fails if the file changed since the AI saw it.

#### XmlPatcher
Ensures structural validity for XML (`pom.xml`):
1.  **Tree Parsing**: Uses `ElementTree` to parse the DOM.
2.  **Logical Removal**: Finds `<plugin>` by ID, not line number.
3.  **Validation**: Runs `mvn validate` before committing.

## 4. Feedback Loop

After execution, the result is stored.
1.  **Success**: Updates the `FeedbackStore` (local JSON or DB).
2.  **Pinecone**: Metadata for the incident vector is tagged "Resolved".
3.  **Next Time**: The Confidence Engine sees this history and boosts the score.
