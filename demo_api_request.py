#!/usr/bin/env python3
"""
Process the actual API request bundle through the workflow
"""

import asyncio
import json
from src.common.types import CorrelationBundle, LogPattern, Event, Metrics, GitConfig
from src.ai.prompt_builder import PromptBuilder
from src.ai.summarizer import Summarizer
from src.ai.error_correlator import ErrorCorrelator

# The actual input from your API request
BUNDLE_DATA = {
    "id": "bundle15012026_01",
    "windowStart": "2026-01-15T07:21:58Z",
    "windowEnd": "2026-01-15T12:51:58Z",
    "rootService": "spring-boot:2.7.15",
    "affectedServices": ["spring-boot:2.7.15", "com.zaxxer.hikari", "org.hibernate"],
    "logPatterns": [
        {
            "pattern": "[WARNING] 'build.plugins.plugin.(groupId:artifactId)' must be unique but found duplicate declaration of plugin org.springframework.boot:spring-boot-maven-plugin @ line 128, column 12",
            "count": 1,
            "firstOccurrence": "2026-01-15T07:21:58Z",
            "lastOccurrence": "2026-01-15T07:21:58Z",
            "severity": "Warning"
        },
        {
            "pattern": "HikariPool-1 - Starting...",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:58Z",
            "lastOccurrence": "2026-01-15T12:51:58Z",
            "severity": None
        },
        {
            "pattern": "HikariPool-1 - Start completed.",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:58Z",
            "lastOccurrence": "2026-01-15T12:51:58Z",
            "severity": None
        },
        {
            "pattern": "Starting DemoBankV1Application using Java 21.0.6",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:53Z",
            "lastOccurrence": "2026-01-15T12:51:53Z",
            "severity": None
        },
        {
            "pattern": "Root WebApplicationContext: initialization completed in 3523 ms",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:57Z",
            "lastOccurrence": "2026-01-15T12:51:57Z",
            "severity": None
        },
        {
            "pattern": "HHH000412: Hibernate ORM core version 5.6.15.Final",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:57Z",
            "lastOccurrence": "2026-01-15T12:51:57Z",
            "severity": None
        },
        {
            "pattern": "Tomcat initialized with port(s): 8070 (http)",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:56Z",
            "lastOccurrence": "2026-01-15T12:51:56Z",
            "severity": None
        },
        {
            "pattern": "jdbcUrl: jdbc:mysql://localhost:3306/demo_bank_v1",
            "count": 1,
            "firstOccurrence": "2026-01-15T12:51:58Z",
            "lastOccurrence": "2026-01-15T12:51:58Z",
            "severity": None  
        }
    ],
    "metrics": {
        "cpuZ": 1.14,
        "latencyZ": 5.7,
        "errorRateZ": 2.0
    },
    "dependencyGraph": ["DemoBankV1Application", "HikariPool", "Hibernate", "MySQL"],
    "git_config": {
        "user_name": "vivekkasula26",
        "user_email": "vivekkasula26@gmail.com"
    }
}


async def process_bundle():
    print("=" * 70)
    print("  PROCESSING YOUR API REQUEST")
    print("=" * 70)
    
    # Convert to CorrelationBundle
    patterns = [
        LogPattern(
            pattern=p["pattern"],
            count=p["count"],
            firstOccurrence=p["firstOccurrence"],
            lastOccurrence=p["lastOccurrence"],
            severity=p.get("severity")
        )
        for p in BUNDLE_DATA["logPatterns"]
    ]
    
    bundle = CorrelationBundle(
        id=BUNDLE_DATA["id"],
        windowStart=BUNDLE_DATA["windowStart"],
        windowEnd=BUNDLE_DATA["windowEnd"],
        rootService=BUNDLE_DATA["rootService"],
        logPatterns=patterns,
        metrics=Metrics(**BUNDLE_DATA["metrics"]),
        dependencyGraph=BUNDLE_DATA["dependencyGraph"],
        git_config=GitConfig(**BUNDLE_DATA["git_config"])
    )
    
    print(f"\n📥 INPUT: CorrelationBundle")
    print(f"   ID: {bundle.id}")
    print(f"   Window: {bundle.windowStart} → {bundle.windowEnd}")
    print(f"   Total Patterns: {len(bundle.logPatterns)}")
    print(f"   Git User: {bundle.git_config.user_name}")
    
    # Step 1: Error Correlation
    print(f"\n🔗 STEP 1: Error Correlation")
    print("-" * 50)
    
    correlation = ErrorCorrelator.correlate(patterns, bundle.dependencyGraph)
    
    if correlation.primary_cluster and correlation.primary_cluster.root_cause:
        root = correlation.primary_cluster.root_cause
        print(f"   🎯 ROOT CAUSE IDENTIFIED:")
        print(f"      Type: {root.severity}")
        print(f"      Pattern: {root.pattern[:80]}...")
        print(f"      Time: {root.firstOccurrence}")
        
        if correlation.primary_cluster.effects:
            print(f"\n   📎 Related ({len(correlation.primary_cluster.effects)}):")
            for e in correlation.primary_cluster.effects[:3]:
                print(f"      → {e.pattern[:50]}...")
    else:
        print("   ℹ️  No errors found - this appears to be a healthy startup log")
    
    print(f"\n   📊 Secondary Clusters: {len(correlation.secondary_clusters)}")
    
    # Step 2: AI Prompt
    print(f"\n🤖 STEP 2: AI Prompt Generation")
    print("-" * 50)
    
    # Build the prompt structure
    correlated = PromptBuilder._format_correlated_patterns(patterns, bundle.dependencyGraph)
    
    print(f"   Structured errorCorrelation for AI:")
    print(json.dumps(correlated, indent=2)[:600])
    
    # Summary for RAG
    print(f"\n📝 STEP 3: RAG Summary")
    print("-" * 50)
    summary = Summarizer.summarize_bundle(bundle)
    print(f"   {summary[:300]}...")
    
    # What AI would recommend
    print(f"\n💡 EXPECTED AI RECOMMENDATION:")
    print("-" * 50)
    print("""
   Based on the WARNING about duplicate Maven plugin:
   
   Root Cause: Duplicate spring-boot-maven-plugin in pom.xml at line 128
   
   Recommended Fix:
   {
     "fix_type": "xml_block_edit",
     "implementation": {
       "file_edits": [{
         "file_path": "pom.xml",
         "xml_selector": "plugin",
         "xml_value": "spring-boot-maven-plugin"
       }]
     }
   }
   
   This would use the XmlPatcher to safely remove the duplicate!
""")


if __name__ == "__main__":
    asyncio.run(process_bundle())
