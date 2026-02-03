"""
Test the Log Ingestion Service with real user logs.
"""

import sys
import os
sys.path.append(os.getcwd())

from src.ingestion import get_log_parser_service

# The actual logs provided by the user
USER_LOGS = """[DEBUG] 2026-01-19T07:43:10.201Z 2026-01-19 13:13:10.195 DEBUG 19944 --- [l-1 housekeeper] com.zaxxer.hikari.pool.HikariPool : HikariPool-1 - Fill pool skipped, pool is at sufficient level.
[DEBUG] 2026-01-19T07:43:10.180Z 2026-01-19 13:13:10.178 DEBUG 19944 --- [l-1 housekeeper] com.zaxxer.hikari.pool.HikariPool : HikariPool-1 - After cleanup stats (total=6, active=0, idle=6, waiting=0)
[DEBUG] 2026-01-19T07:43:10.177Z 2026-01-19 13:12:43.101 DEBUG 19944 --- [ restartedMain] o.s.b.a.ApplicationAvailabilityBean : Application availability state LivenessState changed to CORRECT
[ERROR] 2026-01-19T07:42:58.659Z 2026-01-19 13:12:58.613 DEBUG 19944 --- [0.0-8070-exec-4] o.s.w.s.m.m.a.HttpEntityMethodProcessor : Writing [{timestamp=Mon Jan 19 13:12:58 IST 2026, status=404, error=Not Found, message=No message available, (truncated)...] 2026-01-19 13:12:58.619 DEBUG 19944 --- [0.0-8070-exec-4] o.s.web.servlet.DispatcherServlet : Exiting from "ERROR" dispatch, status 404
[ERROR] 2026-01-19T07:42:58.612Z 2026-01-19 13:12:58.606 DEBUG 19944 --- [0.0-8070-exec-4] o.s.web.servlet.DispatcherServlet : Completed 404 NOT_FOUND 2026-01-19 13:12:58.609 DEBUG 19944 --- [0.0-8070-exec-4] o.s.web.servlet.DispatcherServlet : "ERROR" dispatch for GET "/error?threadsPerService=2", parameters={masked} 2026-01-19 13:12:58.610 DEBUG 19944 --- [0.0-8070-exec-4] s.w.s.m.m.a.RequestMappingHandlerMapping : Mapped to org.springframework.boot.autoconfigure.web.servlet.error.BasicErrorController#error(HttpServletRequest)
[WARN] 2026-01-19T07:42:58.603Z 2026-01-19 13:12:58.604 WARN 19944 --- [0.0-8070-exec-4] o.s.web.servlet.PageNotFound : No mapping for GET /dbpool/LoadSimulationService
[DEBUG] 2026-01-19T07:42:58.602Z 2026-01-19 13:12:58.602 DEBUG 19944 --- [0.0-8070-exec-4] o.s.web.servlet.DispatcherServlet : GET "/dbpool/LoadSimulationService?threadsPerService=2", parameters={masked}
[ERROR] 2026-01-19T07:42:54.867Z 2026-01-19 13:12:54.859 DEBUG 19944 --- [0.0-8070-exec-3] o.s.web.servlet.DispatcherServlet : Exiting from "ERROR" dispatch, status 404
[ERROR] 2026-01-19T07:42:54.852Z 2026-01-19 13:12:54.843 DEBUG 19944 --- [0.0-8070-exec-3] s.w.s.m.m.a.RequestMappingHandlerMapping : Mapped to error
[ERROR] 2026-01-19T07:42:54.843Z 2026-01-19 13:12:54.837 DEBUG 19944 --- [0.0-8070-exec-3] o.s.web.servlet.DispatcherServlet : "ERROR" dispatch for GET "/error?threadsPerService=2"
[WARN] 2026-01-19T07:42:54.834Z 2026-01-19 13:12:54.834 WARN 19944 --- [0.0-8070-exec-3] o.s.web.servlet.PageNotFound : No mapping for GET /dbpool/LoadSimulationService 2026-01-19 13:12:54.834 DEBUG 19944 --- [0.0-8070-exec-3] o.s.web.servlet.DispatcherServlet : Completed 404 NOT_FOUND
[INFO] 2026-01-19T07:42:43.098Z 2026-01-19 13:12:43.099 INFO 19944 --- [ restartedMain] c.b.DemoBank_v1.DemoBankV1Application : Started DemoBankV1Application in 8.67 seconds (JVM running for 9.863)
[INFO] 2026-01-19T07:42:43.063Z 2026-01-19 13:12:43.063 INFO 19944 --- [ restartedMain] o.s.b.w.embedded.tomcat.TomcatWebServer : Tomcat started on port(s): 8070 (http) with context path ''
[WARN] 2026-01-19T07:42:27.313Z [WARNING] Some problems were encountered while building the effective model for com.beko:DemoBank_v1:jar:0.0.1-SNAPSHOT"""


def main():
    print("\n" + "="*60)
    print("OPSCURE LOG INGESTION - REAL USER LOG TEST")
    print("="*60)
    
    # Initialize parser
    parser = get_log_parser_service()
    
    # Parse the logs
    bundle = parser.parse_stream(
        raw_logs=USER_LOGS,
        service_name="demo-bank-v1"
    )
    
    print(f"\n📊 PARSING RESULTS:")
    print(f"   Time Window: {bundle.windowStart} → {bundle.windowEnd}")
    print(f"   Root Service: {bundle.rootService}")
    print(f"   Total Patterns: {len(bundle.logPatterns)}")
    print(f"   Derived Hint: {bundle.derivedRootCauseHint}")
    
    print(f"\n📋 LOG PATTERNS (sorted by severity):")
    
    # Sort by severity for display
    severity_order = {'FATAL': 0, 'ERROR': 1, 'EXCEPTION': 2, 'WARN': 3, 'WARNING': 4, 'INFO': 5, 'DEBUG': 6, None: 7}
    sorted_patterns = sorted(
        bundle.logPatterns, 
        key=lambda p: (severity_order.get(p.errorClass, 7), -p.count)
    )
    
    for idx, pattern in enumerate(sorted_patterns[:10], 1):
        severity_tag = f"[{pattern.errorClass}]" if pattern.errorClass else "[NONE]"
        print(f"   {idx}. {severity_tag} (x{pattern.count}) {pattern.pattern[:80]}...")
    
    # Validate Smart Sorting integration
    print(f"\n✅ VALIDATION:")
    error_count = sum(1 for p in bundle.logPatterns if p.errorClass in ['ERROR', 'FATAL'])
    warn_count = sum(1 for p in bundle.logPatterns if p.errorClass in ['WARN', 'WARNING'])
    debug_count = sum(1 for p in bundle.logPatterns if p.errorClass == 'DEBUG')
    
    print(f"   Errors extracted: {error_count}")
    print(f"   Warnings extracted: {warn_count}")
    print(f"   Debug noise: {debug_count}")
    
    if error_count > 0 and warn_count > 0:
        print(f"\n🎉 SUCCESS: Log Ingestion correctly identified errors and warnings!")
    else:
        print(f"\n❌ ISSUE: Missing error/warning detection")
    
    # Print the bundle as JSON for inspection
    print(f"\n📦 CORRELATION BUNDLE JSON (first 2000 chars):")
    import json
    bundle_json = bundle.model_dump_json(indent=2)
    print(bundle_json[:2000])
    if len(bundle_json) > 2000:
        print("... [truncated]")
    

if __name__ == "__main__":
    main()
