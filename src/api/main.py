"""
Minimal API Entrypoint for AI Pipeline
Exposes endpoints to test the CorrelationBundle → AIRecommendation pipeline.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.common.types import CorrelationBundle, AIRecommendation
from src.ai import get_ai_adapter_service, AIAdapterService
from src.ingestion import get_log_parser_service
from src.api.response_types import IncidentResponse
from src.api.response_mapper import ResponseMapper
from dotenv import load_dotenv


load_dotenv()  # Load .env file


# Lifespan manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    print("[API] Starting Opscure AI Pipeline...")
    
    # Initialize AI Adapter Service
    service = await get_ai_adapter_service()
    app.state.ai_service = service
    
    print("[API] AI Pipeline ready")
    
    yield
    
    # Cleanup
    print("[API] Shutting down...")
    await service.close()
    print("[API] Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Opscure AI Pipeline API",
    description="CorrelationBundle → AIRecommendation pipeline",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

class AnalyzeRequest(BaseModel):
    """Request body for /ai/analyze endpoint"""
    bundle: CorrelationBundle
    use_rag: bool = True
    top_k: int = 5


# =============================================================================
# ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "opscure-ai-pipeline",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check with component health"""
    service: AIAdapterService = app.state.ai_service
    health = await service.health_check()
    
    return {
        "ready": health["status"] != "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        **health
    }


@app.post("/ai/analyze", response_model=IncidentResponse)
async def analyze_correlation_bundle(request: AnalyzeRequest):
    """
    Analyze a CorrelationBundle and return a developer-facing IncidentResponse.

    Flow:
    1. Summarize bundle for embedding
    2. Query Pinecone for similar incidents (RAG)
    3. Build prompt with context
    4. Call LLM with fallback logic
    5. Parse model output into AIRecommendation
    6. Map AIRecommendation → IncidentResponse (developer contract)
    """
    service: AIAdapterService = app.state.ai_service

    try:
        recommendation = await service.create_ai_recommendation(
            bundle=request.bundle,
            use_rag=request.use_rag,
            top_k=request.top_k
        )
        return ResponseMapper.map(recommendation, request.bundle)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/analyze/simple", response_model=IncidentResponse)
async def analyze_bundle_simple(bundle: CorrelationBundle):
    """
    Simplified endpoint — takes a CorrelationBundle directly.
    Uses default settings (RAG enabled, top_k=5).
    """
    service: AIAdapterService = app.state.ai_service
    try:
        recommendation = await service.analyze_bundle(bundle)
        return ResponseMapper.map(recommendation, bundle)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ai/analyze/no-rag", response_model=IncidentResponse)
async def analyze_without_rag(bundle: CorrelationBundle):
    """
    Analyze bundle without RAG context.
    Useful for testing or when Pinecone is unavailable.
    """
    service: AIAdapterService = app.state.ai_service
    try:
        recommendation = await service.analyze_without_rag(bundle)
        return ResponseMapper.map(recommendation, bundle)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/ai/metrics")
async def get_metrics():
    """Get AI service metrics"""
    service: AIAdapterService = app.state.ai_service
    return service.get_metrics()


# =============================================================================
# LOG INGESTION ENDPOINT
# =============================================================================

class IngestRequest(BaseModel):
    """Request body for /ingest endpoint"""
    raw_logs: str
    service_name: Optional[str] = None
    repo_root: Optional[str] = None


class IngestResponse(BaseModel):
    """Response body for /ingest endpoint"""
    bundle: CorrelationBundle
    pattern_count: int
    error_count: int
    time_window_seconds: Optional[float] = None


@app.post("/ingest", response_model=IngestResponse)
async def ingest_logs(request: IngestRequest):
    """
    Ingest raw logs and create a CorrelationBundle.
    
    This endpoint accepts raw log text (multi-line) and parses it into
    a structured CorrelationBundle suitable for AI analysis.
    
    Flow:
    1. Parse each log line (extract timestamp, severity)
    2. Normalize patterns (deduplicate similar logs)
    3. Extract code references from stack traces
    4. Calculate time window and metrics
    5. Return structured CorrelationBundle
    """
    parser = get_log_parser_service(repo_root=request.repo_root)
    
    try:
        bundle = parser.parse_stream(
            raw_logs=request.raw_logs,
            service_name=request.service_name
        )
        
        # Calculate stats
        error_patterns = [p for p in bundle.logPatterns if p.severity in ['ERROR', 'FATAL', 'EXCEPTION']]
        
        return IngestResponse(
            bundle=bundle,
            pattern_count=len(bundle.logPatterns),
            error_count=len(error_patterns)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Log parsing failed: {str(e)}")


@app.post("/ingest/analyze")
async def ingest_and_analyze(request: IngestRequest):
    """
    Ingest raw logs AND immediately analyze them.
    
    Combines /ingest and /ai/analyze into a single call.
    This is the recommended endpoint for end-to-end processing.
    """
    parser = get_log_parser_service(repo_root=request.repo_root)
    service: AIAdapterService = app.state.ai_service
    
    try:
        # Step 1: Parse logs into bundle
        bundle = parser.parse_stream(
            raw_logs=request.raw_logs,
            service_name=request.service_name
        )
        
        # Step 2: Analyze bundle with AI
        recommendation = await service.analyze_bundle(bundle)
        
        return {
            "bundle": bundle,
            "recommendation": recommendation,
            "pattern_count": len(bundle.logPatterns)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# EXAMPLE ENDPOINT (FOR TESTING)
# =============================================================================

@app.get("/ai/example-bundle")
async def get_example_bundle():
    """
    Return an example CorrelationBundle for testing.
    Can be used as input to /ai/analyze.
    """
    from src.common.types import LogPattern, Event, Metrics, SequenceItem
    
    example = CorrelationBundle(
        id="corr_example_001",
        windowStart="2024-12-04T10:30:00Z",
        windowEnd="2024-12-04T10:35:00Z",
        rootService="database",
        affectedServices=["database", "api-gateway", "auth-service"],
        logPatterns=[
            LogPattern(
                pattern="ERROR: Connection pool exhausted, cannot acquire connection",
                count=47,
                firstOccurrence="2024-12-04T10:30:15Z",
                lastOccurrence="2024-12-04T10:34:58Z",
                severity="ConnectionPoolError"
            ),
            LogPattern(
                pattern="WARN: Query timeout after 30000ms",
                count=23,
                firstOccurrence="2024-12-04T10:30:20Z",
                lastOccurrence="2024-12-04T10:34:45Z",
                severity="QueryTimeout"
            )
        ],
        events=[
            Event(
                id="evt_001",
                type="Warning",
                reason="HighLatency",
                service="database",
                pod="postgres-0",
                timestamp="2024-12-04T10:30:10Z"
            ),
            Event(
                id="evt_002",
                type="Warning",
                reason="BackendConnectionFailure",
                service="api-gateway",
                pod="api-gateway-abc123",
                timestamp="2024-12-04T10:30:18Z"
            )
        ],
        metrics=Metrics(
            cpuZ=2.8,
            memZ=1.5,
            latencyZ=4.2,
            errorRateZ=3.9
        ),
        dependencyGraph=["database", "api-gateway", "auth-service", "frontend"],
        sequence=[
            SequenceItem(
                timestamp="2024-12-04T10:30:10Z",
                type="metric",
                message="CPU spike detected on database",
                sequenceIndex=0
            ),
            SequenceItem(
                timestamp="2024-12-04T10:30:15Z",
                type="log",
                message="Connection pool exhausted",
                sequenceIndex=1
            ),
            SequenceItem(
                timestamp="2024-12-04T10:30:18Z",
                type="event",
                message="Backend connection failure on api-gateway",
                sequenceIndex=2
            )
        ],
        derivedRootCauseHint="Database connection pool exhaustion suspected"
    )
    
    return example


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

