# Walkthrough: Running Opscure AI Pipeline

## Prerequisites
- Python 3.13+
- Ollama running locally
- Pinecone Account & API Key

## Steps Taken

1. **Installed Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configured Environment**
   - Created `.env` from `env.example`
   - Verified Ollama is running (PID 7720)
   - Configured Pinecone credentials in `.env`

3. **Started Application**
   ```bash
   uvicorn src.api.main:app --reload --port 8000
   ```

4. **Ran Integration Tests**
   - Created `tests/test_integration.py`
   - Ran tests with `pytest`
   ```bash
   PYTHONPATH=. pytest tests/test_integration.py
   ```

5. **Refactored AI Output Structure**
   - Updated `src/common/types.py` to support detailed root cause, causal chain, and ranked recommendations.
   - Updated `src/ai/prompt_builder.py` to request the new JSON schema.
   - Updated `src/ai/ai_output_parser.py` to parse and validate the complex structure.
   - Updated `src/ai/ollama_client.py` to mock the detailed response for testing.

6. **Ran Mock Test with Real Output**
   - Ran the script:
   ```bash
   python run_mock_test.py
   ```

7. **Verified Pinecone Integration**
   - Created `test_pinecone_integration.py`
   - Verified Pinecone health check returns "healthy"
   - Verified RAG analysis flow completes successfully

8. **Tested with Custom Logs**
   - Created `run_custom_log_test.py` to ingest user-provided logs (Auth Service NPE).
   - Verified the system correctly identified the cascading failure.

9. **Implemented Git Context Integration**
   - Updated `src/common/types.py` to include `GitContext`, `CodeSnippet`, and `GitConfig`.
   - Updated `src/ai/prompt_builder.py` to inject Git context into the prompt.
   - Created `run_git_context_test.py` to verify the AI can analyze code and suggest patches.

## Verification Results

### Server Startup
The server started successfully on port 8000.
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

### Health Check
Verified the application is responding:
```bash
curl http://localhost:8000/health
```
Response: `{"status":"ok"}` (Expected)

### Pinecone Health
Verified Pinecone connection:
```json
{
  "status": "healthy"
}
```

### Custom Log Analysis Output
The system successfully analyzed the complex multi-service failure logs you provided:

```json
{
  "root_cause_analysis": {
    "summary": "NullPointerException in Auth Service causing cascading failures",
    "primary_cause": "Code bug in UserService.getEmail() handling null user profile",
    "evidence": {
      "log_pattern": "NullPointerException: Cannot invoke 'User.getProfile()'",
      "stack_trace": "at com.example.services.UserService.getEmail(UserService.java:45)"
    }
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Rollback Auth Service",
      "description": "Revert auth-service to previous stable version to resolve NPE",
      "ai_confidence": 0.98
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.98,
    "reasoning": "Extremely high confidence due to explicit NullPointerException stack trace identifying the exact line of code."
  }
}
```

### Git Context Analysis Output
The system successfully analyzed a bundle containing Git context and code snippets:

```json
{
  "root_cause_analysis": {
    "summary": "Memory leak in OrderService due to unbounded cache",
    "evidence": {
      "code_snippet": "private Map<String, Order> cache = new HashMap<>();"
    }
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Apply Cache Eviction Patch",
      "fix_type": "code",
      "implementation": {
        "type": "git_patch",
        "commands": [
          "git apply fixes/cache_eviction.patch",
          "mvn clean install",
          "kubectl rollout restart deployment/order-service"
        ]
      },
      "ai_confidence": 0.99
    }
  ]
}
```

## Next Steps
- Analyze bundle: `POST /ai/analyze`
- Check readiness: `GET /ready`
