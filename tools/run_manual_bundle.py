
import asyncio
import os
from unittest.mock import AsyncMock, MagicMock
from src.common.types import CorrelationBundle
from src.ai.ai_adapter_service import AIAdapterService
from src.ai.groq_client import GroqClient
from src.ai.ollama_client import OllamaClient
from src.remediation.confidence import ConfidenceResult
from src.remediation.safety import SafetyLevel, SafetyPolicy
from src.ai.agent import RemediationAgent

# Dev bundle from incident_20260225_191358 — GitHub API rate limit error
# Outer SDK format is [{bundle: {...}}] — we unwrap to the inner bundle object directly.
CUSTOM_BUNDLE_DATA = {
    "id": "incident_20260225_191358",
    "windowStart": "2026-02-25T19:13:58Z",
    "windowEnd": "2026-02-25T19:13:58Z",
    "logPatterns": [
        {
            "pattern": (
                "<NUM>-<NUM>-<NUM> <NUM>:<NUM>:<NUM>.<NUM> ERROR "
                "[http-nio-<NUM>.<NUM>.<NUM>.<NUM>-<NUM>-exec-<NUM>] "
                "c.b.D.controllers.SimulateAPIQuota - Error on request <NUM>\n"
                "org.springframework.web.client.HttpClientErrorException$Forbidden: "
                "<NUM> rate limit exceeded: "
                '"{\"message\":\"API rate limit exceeded for <NUM>.<NUM>.<NUM>.<NUM>. '
                "(But here's the good news: Authenticated requests get a higher rate limit. "
                'Check out the documentation for more details.)\",'
                '\"documentation_url\":\"https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting\"}<EOL>\"\n'
                "\tat org.springframework.web.client.HttpClientErrorException.create(HttpClientErrorException.java:<NUM>)\n"
                "\tat org.springframework.web.client.DefaultResponseErrorHandler.handleError(DefaultResponseErrorHandler.java:<NUM>)\n"
                "\tat org.springframework.web.client.DefaultResponseErrorHandler.handleError(DefaultResponseErrorHandler.java:<NUM>)\n"
                "\tat org.springframework.web.client.ResponseErrorHandler.handleError(ResponseErrorHandler.java:<NUM>)\n"
                "\tat org.springframework.web.client.RestTemplate.handleResponse(RestTemplate.java:<NUM>)\n"
                "\tat org.springframework.web.client.RestTemplate.doExecute(RestTemplate.java:<NUM>)\n"
                "\tat org.springframework.web.client.RestTemplate.execute(RestTemplate.java:<NUM>)\n"
                "\tat org.springframework.web.client.RestTemplate.getForEntity(RestTemplate.java:<NUM>)\n"
                "\tat com.beko.DemoBank_v<NUM>.controllers.SimulateAPIQuota.spamGitHub(SimulateAPIQuota.java:<NUM>)\n"
                "\tat java.base/jdk.internal.reflect.DirectMethodHandleAccessor.invoke(Unknown Source)\n"
                "\tat java.base/java.lang.reflect.Method.invoke(Unknown Source)\n"
                "\tat org.springframework.web.method.support.InvocableHandlerMethod.doInvoke(InvocableHandlerMethod.java:<NUM>)\n"
                "\tat org.springframework.web.method.support.InvocableHandlerMethod.invokeForRequest(InvocableHandlerMethod.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.mvc.method.annotation.ServletInvocableHandlerMethod.invokeAndHandle(ServletInvocableHandlerMethod.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter.invokeHandlerMethod(RequestMappingHandlerAdapter.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerAdapter.handleInternal(RequestMappingHandlerAdapter.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.mvc.method.AbstractHandlerMethodAdapter.handle(AbstractHandlerMethodAdapter.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.DispatcherServlet.doDispatch(DispatcherServlet.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.DispatcherServlet.doService(DispatcherServlet.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.FrameworkServlet.processRequest(FrameworkServlet.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.FrameworkServlet.doGet(FrameworkServlet.java:<NUM>)\n"
                "\tat javax.servlet.http.HttpServlet.service(HttpServlet.java:<NUM>)\n"
                "\tat org.springframework.web.servlet.FrameworkServlet.service(FrameworkServlet.java:<NUM>)\n"
                "\tat javax.servlet.http.HttpServlet.service(HttpServlet.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.apache.tomcat.websocket.server.WsFilter.doFilter(WsFilter.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.springframework.web.filter.CorsFilter.doFilterInternal(CorsFilter.java:<NUM>)\n"
                "\tat org.springframework.web.filter.OncePerRequestFilter.doFilter(OncePerRequestFilter.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.springframework.web.filter.CharacterEncodingFilter.doFilterInternal(CharacterEncodingFilter.java:<NUM>)\n"
                "\tat org.springframework.web.filter.OncePerRequestFilter.doFilter(OncePerRequestFilter.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.internalDoFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.apache.catalina.core.ApplicationFilterChain.doFilter(ApplicationFilterChain.java:<NUM>)\n"
                "\tat org.apache.catalina.core.StandardWrapperValve.invoke(StandardWrapperValve.java:<NUM>)\n"
                "\tat org.apache.catalina.core.StandardContextValve.invoke(StandardContextValve.java:<NUM>)\n"
                "\tat org.apache.catalina.authenticator.AuthenticatorBase.invoke(AuthenticatorBase.java:<NUM>)\n"
                "\tat org.apache.catalina.core.StandardHostValve.invoke(StandardHostValve.java:<NUM>)\n"
                "\tat org.apache.catalina.valves.ErrorReportValve.invoke(ErrorReportValve.java:<NUM>)\n"
                "\tat org.apache.catalina.core.StandardEngineValve.invoke(StandardEngineValve.java:<NUM>)\n"
                "\tat org.apache.catalina.connector.CoyoteAdapter.service(CoyoteAdapter.java:<NUM>)\n"
                "\tat org.apache.coyote.http<NUM>.Http<NUM>Processor.service(Http<NUM>Processor.java:<NUM>)\n"
                "\tat org.apache.coyote.AbstractProcessorLight.process(AbstractProcessorLight.java:<NUM>)\n"
                "\tat org.apache.coyote.AbstractProtocol$ConnectionHandler.process(AbstractProtocol.java:<NUM>)\n"
                "\tat org.apache.tomcat.util.net.NioEndpoint$SocketProcessor.doRun(NioEndpoint.java:<NUM>)\n"
                "\tat org.apache.tomcat.util.net.SocketProcessorBase.run(SocketProcessorBase.java:<NUM>)\n"
                "\tat org.apache.tomcat.util.threads.ThreadPoolExecutor.runWorker(ThreadPoolExecutor.java:<NUM>)\n"
                "\tat org.apache.tomcat.util.threads.ThreadPoolExecutor$Worker.run(ThreadPoolExecutor.java:<NUM>)\n"
                "\tat org.apache.tomcat.util.threads.TaskThread$WrappingRunnable.run(TaskThread.java:<NUM>)\n"
                "\tat java.base/java.lang.Thread.run(Unknown Source)"
            ),
            "count": 1,
            "severity": "ERROR",
            "rootService": "banking app",
            "affectedService": ["banking app"],
            "logSource": {},
        }
    ],
    "events": [],
    "metrics": {},
    "dependencyGraph": [],
    "gitConfig": {},
    "flush_metadata": {
        "reason": "error_detected",
        "log_count": 1,
        "flushed_at": "2026-02-26T06:37:05Z"
    },
}


# Mock AI Response to simulate a realistic analysis of these logs
# Since these are INFO logs, a real AI might say "No Error".
# But to demonstrate the workflow, let's assume the user thinks there IS an issue or wants to see the "Healthy" state.
# OR, lets assume the logs stopped abruptly implying a crash? 
# Let's return a "Status Report" style response.
MOCK_AI_ANALYSIS = """
{
  "root_cause_analysis": {
    "primary_cause": "GitHub API rate limit exceeded due to unauthenticated requests",
    "summary": "SimulateAPIQuota.spamGitHub() is calling the GitHub REST API without authentication. Unauthenticated requests are capped at 60/hr per IP. The 403 Forbidden response confirms the limit was hit.",
    "impact": "All calls to spamGitHub() fail with 403 until the rate limit window resets (1 hour).",
    "contributing_factors": [
      "No Authorization header on RestTemplate",
      "No retry/backoff strategy",
      "No rate limit pre-check before looping requests"
    ],
    "timeline": [
      "2026-02-25T19:13:58Z - First 403 from GitHub API on /rate_limit or similar endpoint"
    ],
    "evidence": {
      "log_pattern": "HttpClientErrorException$Forbidden: 403 rate limit exceeded",
      "class": "com.beko.DemoBank_v*.controllers.SimulateAPIQuota",
      "method": "spamGitHub()"
    }
  },
  "recommendations": [
    {
      "rank": 1,
      "title": "Add GitHub PAT to RestTemplate Authorization header",
      "description": "Inject a GitHub Personal Access Token via environment variable and set it as a Bearer token on the RestTemplate used in spamGitHub().",
      "fix_type": "local_file_edit",
      "risk_level": "Low",
      "estimated_effort": "Low",
      "estimated_time_minutes": 15,
      "cost_impact": "None",
      "implementation": {
        "type": "local_file_edit",
        "commands": [],
        "pre_checks": ["Verify GITHUB_TOKEN env var is set"],
        "post_checks": ["Confirm response status is 200 after adding token"]
      },
      "ai_confidence": 0.95,
      "reasoning": "GitHub explicitly states authenticated requests get higher limits. Token auth is the standard fix.",
      "side_effects": [],
      "rollback": null
    }
  ],
  "confidence_assessment": {
    "final_confidence": 0.95,
    "action": "manual_review",
    "threshold_used": 0.99,
    "risk_level": "Low",
    "breakdown": {},
    "adjustments": {},
    "reasoning": "Root cause is clear from the error message. Fix is well-understood but requires a secret (PAT) which needs human action.",
    "decision_factors": {}
  },
  "causal_chain": [],
  "requires_human_review": true,
  "auto_heal_candidate": false
}
"""

async def run_pipeline():
    print(f"\n🚀 Processing Bundle: {CUSTOM_BUNDLE_DATA['id']}")
    print("==================================================")
    
    # 1. Hydrate Bundle
    from src.common.git_utils import GitConfigCollector
    from dotenv import load_dotenv
    load_dotenv()

    git_config = GitConfigCollector.collect_config(".")
    
    bundle = CorrelationBundle.model_validate(CUSTOM_BUNDLE_DATA)
    if git_config:
        bundle.git_config = git_config
        name = git_config.user_name or "(no name)"
        email = git_config.user_email or "(no email)"
        print(f"✅ Loaded Git Config: {name} <{email}>")
    else:
        print("⚠️  No local git config — auto-fix PR generation disabled")
    
    # 2. Setup real Groq LLM
    print("\n🔌 Connecting to Groq LLM...")
    groq_client = GroqClient()
    service = AIAdapterService(llm_client=groq_client)

    # 3. Run full pipeline: RAG → prompt → LLM → parse → map
    print("🧠 Running AI analysis (RAG + LLM)...\n")
    try:
        recommendation = await service.create_ai_recommendation(
            bundle=bundle,
            use_rag=True,
            top_k=5
        )
    except Exception as e:
        print(f"❌ Pipeline failed: {e}")
        raise

    # 4. Print results
    rca = recommendation.root_cause_analysis
    ca  = recommendation.confidence_assessment
    recs = recommendation.recommendations

    print("=" * 54)
    print("✅ AI ANALYSIS COMPLETE")
    print("=" * 54)
    print(f"  Incident ID : {recommendation.incident_id}")
    print(f"  Analyzed at : {recommendation.analyzed_at}")
    print(f"  Model time  : {recommendation.processing_time_ms:.0f}ms")
    print()
    print("── Root Cause Analysis ─────────────────────────────")
    print(f"  Primary Cause : {rca.primary_cause}")
    print(f"  Summary       : {rca.summary}")
    print(f"  Impact        : {rca.impact}")
    if rca.contributing_factors:
        print(f"  Contributing  : {', '.join(rca.contributing_factors)}")
    print()
    print("── Confidence Assessment ─────────────────────────────")
    print(f"  Score   : {ca.final_confidence:.0%}")
    print(f"  Action  : {ca.action}")
    print(f"  Risk    : {ca.risk_level}")
    print(f"  Reason  : {ca.reasoning}")
    print()
    print(f"── Recommendations ({len(recs)}) ──────────────────────────────")
    for rec in recs:
        print(f"  [{rec.rank}] {rec.title}")
        print(f"      Type     : {rec.fix_type}")
        print(f"      Effort   : {rec.estimated_effort} (~{rec.estimated_time_minutes}min)")
        print(f"      AI Conf  : {rec.ai_confidence:.0%}")
        print(f"      Reasoning: {rec.reasoning}")
        if rec.implementation and rec.implementation.commands:
            print(f"      Commands : {rec.implementation.commands}")
        print()
    print(f"  Requires human review : {recommendation.requires_human_review}")
    print(f"  Auto-heal candidate   : {recommendation.auto_heal_candidate}")
    print("=" * 54)

    # 5. Run RemediationAgent (safety gate)
    print("\n🤖 Agent Safety Evaluation...")
    from src.api.response_mapper import ResponseMapper
    from src.ai.agent import RemediationAgent

    # Agent works on proposals — use the adapter's internal proposal builder
    proposal = await service.create_remediation_proposal(bundle)
    if proposal:
        agent = RemediationAgent()
        result = agent.run(proposal)
        print(f"\n🏁 Agent Decision : {result.confidence_result.decision.name}")
        print(f"   Reason         : {result.confidence_result.reason}")
        for log in result.execution_logs:
            print(f"   - {log}")
    else:
        print("⚠️  Proposal generation skipped (no proposal returned)")



if __name__ == "__main__":
    asyncio.run(run_pipeline())
