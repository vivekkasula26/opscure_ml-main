
import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

from src.ai.prompt_builder import PromptBuilder
from src.ai.summarizer import Summarizer
from src.common.types import CorrelationBundle, LogPattern

def run_demo():
    print("\n=== Opscure Log Sorting Demo ===")
    print("Simulating ingestion of user-provided logs...\n")
    
    # 1. Simulate the User's Log Data
    # We purposefully inflate the noise counts to test the sorting Limits
    
    patterns = [
        # NOISE (High Volume)
        LogPattern(
            pattern="[DEBUG] com.zaxxer.hikari.pool.HikariPool : HikariPool-1 - Fill pool skipped, pool is at sufficient level.",
            count=150, # High noise
            firstOccurrence="2026-01-19T07:43:10.201Z",
            lastOccurrence="2026-01-19T07:43:10.201Z"
        ),
        LogPattern(
            pattern="[DEBUG] com.zaxxer.hikari.pool.HikariPool : HikariPool-1 - Before cleanup stats (total=6, active=0, idle=6, waiting=0)",
            count=120,
            firstOccurrence="2026-01-19T07:43:10.177Z",
            lastOccurrence="2026-01-19T07:43:10.177Z"
        ),
        LogPattern(
            pattern="[DEBUG] o.s.web.servlet.DispatcherServlet : Exiting from 'ERROR' dispatch, status 404",
            count=15, # Medium noise (Debug logs about errors)
            firstOccurrence="2026-01-19T07:42:58.619Z",
            lastOccurrence="2026-01-19T07:42:58.619Z"
        ),
        LogPattern(
            pattern="[INFO] o.apache.catalina.core.StandardService : Starting service [Tomcat]",
            count=50,
            firstOccurrence="2026-01-19T07:42:38.336Z",
            lastOccurrence="2026-01-19T07:42:38.336Z"
        ),
        
        # SIGNAL (Low Volume, Critical)
        LogPattern(
            pattern="[ERROR] o.s.web.servlet.DispatcherServlet : Completed 404 NOT_FOUND",
            count=5, 
            firstOccurrence="2026-01-19T07:42:58.612Z", 
            lastOccurrence="2026-01-19T07:42:58.612Z",
            errorClass="404_NOT_FOUND"
        ),
        LogPattern(
            pattern="[WARN] o.s.web.servlet.PageNotFound : No mapping for GET /dbpool/LoadSimulationService",
            count=3,
            firstOccurrence="2026-01-19T07:42:58.603Z",
            lastOccurrence="2026-01-19T07:42:58.603Z",
            errorClass="PageNotFound"
        ),
        LogPattern(
            pattern="[WARN] 'build.plugins.plugin.(groupId:artifactId)' must be unique but found duplicate",
            count=1,
            firstOccurrence="2026-01-19T07:42:27.313Z",
            lastOccurrence="2026-01-19T07:42:27.313Z",
            errorClass="MavenBuildWarning"
        )
    ]
    
    # Add more noise to reach > 20 patterns to force truncation
    for i in range(30):
        patterns.append(LogPattern(
            pattern=f"[DEBUG] org.springframework.boot.loader.JarLauncher : Loading class {i}",
            count=10,
            firstOccurrence="2026-01-19T07:42:00.000Z",
            lastOccurrence="2026-01-19T07:42:00.000Z"
        ))
        
    print(f"Total Unique Patterns: {len(patterns)}")
    print(f"Total Log Events Simulated: {sum(p.count for p in patterns)}")
    
    bundle = CorrelationBundle(
        windowStart="Now",
        windowEnd="Now",
        logPatterns=patterns
    )
    
    # --- Execute Sort ---
    print("\n--- Running Smart Sort (Priority Check) ---")
    prioritized = PromptBuilder._get_prioritized_patterns(bundle.logPatterns, limit=10)
    
    print(f"Selecting Top {len(prioritized)} for AI Prompt:")
    for idx, p in enumerate(prioritized):
        print(f"#{idx+1} [{p.count}x] {p.pattern[:100]}...")
        
    # Validation
    top_patterns_text = [p.pattern for p in prioritized]
    has_error = any("[ERROR]" in p for p in top_patterns_text)
    has_warn = any("[WARN]" in p for p in top_patterns_text)
    
    if has_error and has_warn:
        print("\n✅ SUCCESS: ERROR and WARN logs bubbled to the top despite low counts.")
    else:
        print("\n❌ FAILURE: Critical logs missing from top selection.")
        
    # --- Execute Summary ---
    print("\n--- Generating Embeddings Summary ---")
    summary = Summarizer.summarize_bundle(bundle)
    print(f"Summary: {summary}")

if __name__ == "__main__":
    run_demo()
