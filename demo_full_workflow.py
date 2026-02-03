#!/usr/bin/env python3
"""
Opscure End-to-End Workflow Demo

Demonstrates the complete flow:
  Raw Logs → Parse → Correlate → AI Analysis → Remediation

Run: python3 demo_full_workflow.py
"""

import asyncio
from src.ingestion.log_parser import LogParserService
from src.ai.prompt_builder import PromptBuilder
from src.ai.summarizer import Summarizer
from src.ai.error_correlator import ErrorCorrelator

# ============================================================================
# STEP 1: RAW INPUT (This is what you provide)
# ============================================================================

RAW_LOGS = """
2026-01-26T18:20:00.123Z [ERROR] com.example.DatabasePool - Connection pool exhausted. 
    Active connections: 50/50, waiting queue: 127
    at com.example.DatabasePool.getConnection(DatabasePool.java:89)
2026-01-26T18:20:00.456Z [ERROR] com.example.UserService - Failed to fetch user profile
    Caused by: java.sql.SQLException: Cannot acquire connection from pool
    at com.example.UserService.getUser(UserService.java:45)
2026-01-26T18:20:00.789Z [ERROR] com.example.PaymentService - Payment processing failed
    Caused by: UserNotFoundException: Could not load user for payment
    at com.example.PaymentService.process(PaymentService.java:112)
2026-01-26T18:20:01.000Z [ERROR] com.example.APIGateway - Request failed with 500
    POST /api/checkout returned Internal Server Error
2026-01-26T18:25:00.000Z [WARN] com.example.CertManager - SSL certificate for api.example.com 
    expires in 7 days. Consider renewal.
2026-01-26T18:25:01.000Z [INFO] com.example.HealthCheck - All services responding
"""

# Your service dependency graph (how services call each other)
DEPENDENCY_GRAPH = ["api-gateway", "payment-service", "user-service", "database"]


async def run_demo():
    print("=" * 70)
    print("  OPSCURE WORKFLOW DEMO: Raw Logs → AI Recommendation")
    print("=" * 70)
    
    # ========================================================================
    # STEP 2: Parse raw logs into CorrelationBundle
    # ========================================================================
    print("\n📥 STEP 1: Parsing Raw Logs...")
    print("-" * 50)
    
    parser = LogParserService()
    bundle = parser.parse_stream(RAW_LOGS, service_name="checkout-service")
    
    # Add dependency graph for correlation
    bundle.dependencyGraph = DEPENDENCY_GRAPH
    
    print(f"   Bundle ID: {bundle.id}")
    print(f"   Time Window: {bundle.windowStart} → {bundle.windowEnd}")
    print(f"   Root Service: {bundle.rootService}")
    print(f"   Patterns Found: {len(bundle.logPatterns)}")
    print(f"   Error Rate Z-Score: {bundle.metrics.errorRateZ}")
    
    # ========================================================================
    # STEP 3: Error Correlation (Group related errors)
    # ========================================================================
    print("\n🔗 STEP 2: Correlating Errors...")
    print("-" * 50)
    
    correlation = ErrorCorrelator.correlate(bundle.logPatterns, bundle.dependencyGraph)
    
    if correlation.primary_cluster:
        print(f"   PRIMARY CLUSTER:")
        print(f"     Root Cause: {correlation.primary_cluster.root_cause.pattern[:60]}...")
        print(f"     Related Errors: {len(correlation.primary_cluster.effects)}")
        for effect in correlation.primary_cluster.effects[:3]:
            print(f"       → {effect.pattern[:50]}...")
    
    if correlation.secondary_clusters:
        print(f"\n   SECONDARY CLUSTERS: {len(correlation.secondary_clusters)}")
        for cluster in correlation.secondary_clusters:
            if cluster.root_cause:
                print(f"     • {cluster.root_cause.pattern[:50]}...")
    
    # ========================================================================
    # STEP 4: Build Summary for Embedding (RAG)
    # ========================================================================
    print("\n📝 STEP 3: Building Summary for RAG...")
    print("-" * 50)
    
    summary = Summarizer.summarize_bundle(bundle)
    print(f"   Summary ({len(summary)} chars):")
    print(f"   \"{summary[:200]}...\"")
    
    # ========================================================================
    # STEP 5: Build Prompt for AI
    # ========================================================================
    print("\n🤖 STEP 4: Building AI Prompt...")
    print("-" * 50)
    
    prompt = PromptBuilder.build_prompt(bundle, similar_incidents=[])
    print(f"   Prompt length: {len(prompt)} chars")
    print(f"   Includes errorCorrelation with root cause identification")
    
    # ========================================================================
    # STEP 6: Show what AI would receive
    # ========================================================================
    print("\n📤 STEP 5: AI Input Preview (errorCorrelation section)...")
    print("-" * 50)
    
    import json
    correlated = PromptBuilder._format_correlated_patterns(
        bundle.logPatterns, 
        bundle.dependencyGraph
    )
    print(json.dumps(correlated, indent=2)[:800] + "...")
    
    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("  WORKFLOW COMPLETE")
    print("=" * 70)
    print("""
Next Steps (requires API keys):
  1. Pinecone would embed the summary and find similar past incidents
  2. Groq/Ollama would analyze the prompt and return AIRecommendation
  3. RemediationAgent would evaluate and execute the fix
  
To run full pipeline with AI:
  python3 run_custom_log_test.py
""")


if __name__ == "__main__":
    asyncio.run(run_demo())
