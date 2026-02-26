"""
End-to-End Validation: Bundle → ResponseMapper → IncidentResponse

Runs without pydantic by mocking BaseModel as a plain namespace.
Exercises the full ResponseMapper logic and validates the output shape.
"""

import sys, types, json

# ── Mock pydantic so we can import without installing it ──────────────────────
class _Field:
    def __init__(self, default=None, default_factory=None, alias=None, serialization_alias=None):
        self.default = default
        self.default_factory = default_factory
        self.alias = alias
        self.serialization_alias = serialization_alias

def Field(default=None, default_factory=None, alias=None, serialization_alias=None, **kwargs):
    return _Field(default, default_factory, alias, serialization_alias)

class BaseModel:
    model_config = {}
    def __init__(self, **kwargs):
        # Apply defaults from annotations
        for name, annotation in self.__class__.__annotations__.items():
            class_val = getattr(self.__class__, name, None)
            if isinstance(class_val, _Field):
                if name in kwargs:
                    setattr(self, name, kwargs[name])
                elif class_val.default_factory:
                    setattr(self, name, class_val.default_factory())
                else:
                    setattr(self, name, class_val.default)
            else:
                setattr(self, name, kwargs.get(name, class_val))

    def model_dump(self):
        result = {}
        for name in self.__class__.__annotations__:
            val = getattr(self, name, None)
            field_def = getattr(self.__class__, name, None)
            # Use serialization_alias if set
            key = name
            if isinstance(field_def, _Field) and field_def.serialization_alias:
                key = field_def.serialization_alias
            if isinstance(val, BaseModel):
                result[key] = val.model_dump()
            elif isinstance(val, list):
                result[key] = [v.model_dump() if isinstance(v, BaseModel) else v for v in val]
            else:
                result[key] = val
        return result

pydantic_mock = types.ModuleType("pydantic")
pydantic_mock.BaseModel = BaseModel
pydantic_mock.Field = Field
sys.modules["pydantic"] = pydantic_mock
sys.modules["dotenv"] = types.ModuleType("dotenv")
sys.modules["dotenv"].load_dotenv = lambda: None

# ── Now import project code ───────────────────────────────────────────────────
from src.common.types import (
    CorrelationBundle, LogPattern, LogSource, GitContext, GitConfig,
    FlushMetadata, Metrics, Event, AIRecommendation, RootCauseAnalysis,
    CausalChainStep, Recommendation, ConfidenceAssessment,
    ImplementationDetails, FileEdit, RollbackPlan, SimilarCase
)
# Import response_types and response_mapper directly (avoid api/__init__ → fastapi)
import importlib.util, pathlib

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

ROOT = pathlib.Path("/Users/supreeth/Downloads/opscure_ml-main")
_load("src.api.response_types", ROOT / "src/api/response_types.py")
_load("src.api.response_mapper", ROOT / "src/api/response_mapper.py")

from src.api.response_types import (
    IncidentResponse, DiagnosisSummary, FixItem,
    FileEdit as ResponseFileEdit, IncidentMeta
)
from src.api.response_mapper import ResponseMapper


# ── Build a realistic CorrelationBundle ──────────────────────────────────────
bundle = CorrelationBundle(
    windowStart="2026-02-24T22:00:00Z",
    windowEnd="2026-02-24T22:05:00Z",
    rootService="payment-service",
    affectedServices=["payment-service"],
    logPatterns=[
        LogPattern(
            pattern="ERROR java.sql.SQLException: Cannot acquire connection from pool\n    at HikariPool.getConnection(HikariPool.java:89)",
            count=12,
            firstOccurrence="2026-02-24T22:03:30Z",
            lastOccurrence="2026-02-24T22:05:00Z",
            severity="ERROR",
            rootService="payment-service",
            affectedService="payment-service",
            logSource=LogSource(
                type="application",
                container="payment-service-7d4f8b-xkz2p",
                namespace="production"
            )
        ),
        LogPattern(
            pattern="WARN HikariPool-1 - Connection pool approaching limit: 48/50 active",
            count=3,
            firstOccurrence="2026-02-24T22:01:00Z",
            lastOccurrence="2026-02-24T22:02:00Z",
            severity="WARNING",
            rootService="payment-service",
            affectedService="payment-service",
        )
    ],
    flush_metadata=FlushMetadata(
        reason="error_detected",
        log_count=18,
        flushed_at="2026-02-24T22:05:01Z"
    ),
    git_context=GitContext(
        repo_url="https://github.com/company/checkout-service",
        branch="main",
        commit_hash="a1b2c3d4e5f6",
        recent_commits=["a1b2c3d Update HikariCP config - dev@company.com"],
        changed_files=[
            "src/main/resources/application.yml",
            "src/main/java/com/acme/payment/config/DatabaseConfig.java"
        ],
        diff="diff --git a/application.yml\n-  connection-timeout: 30000\n+  connection-timeout: 5000"
    ),
    git_config=GitConfig(user_name="ops-bot", user_email="ops@company.com"),
    metrics=Metrics(cpuZ=2.1, memZ=3.8, latencyZ=4.5, errorRateZ=6.2)
)

# ── Build a realistic AIRecommendation ───────────────────────────────────────
recommendation = AIRecommendation(
    correlation_bundle_id=bundle.id,
    root_cause_analysis=RootCauseAnalysis(
        summary="Database queries timing out due to HikariCP pool size (5) and timeout (5s), introduced in commit a1b2c3d.",
        primary_cause="HikariCP connection-timeout reduced from 30s to 5s and pool size from 20 to 5 in last commit",
        contributing_factors=["Recent config commit", "High checkout load"],
        timeline=[
            "Commit a1b2c3d reduced pool config",
            "Pool exhausted under normal load (48/50 → 49/50 → ERROR)",
            "All checkout requests failing with SQLException"
        ],
        evidence={"commit": "a1b2c3d", "pattern_count": 12},
        impact="All checkout requests failing"
    ),
    causal_chain=[
        CausalChainStep(step=1, event="Config change deployed", timestamp="2026-02-24T21:40:00Z"),
        CausalChainStep(step=2, event="Pool approaching limit", timestamp="2026-02-24T22:01:00Z"),
        CausalChainStep(step=3, event="Pool exhausted", timestamp="2026-02-24T22:03:30Z"),
    ],
    recommendations=[
        Recommendation(
            rank=1,
            title="Increase HikariCP timeout and pool size",
            description="Revert connection-timeout to 30s and pool size to 20 in application.yml",
            fix_type="local_file_edit",
            estimated_effort="low",
            estimated_time_minutes=5,
            risk_level="low",
            cost_impact="none",
            implementation=ImplementationDetails(
                type="local_file_edit",
                commands=[],
                file_edits=[
                    FileEdit(
                        file_path="src/main/resources/application.yml",
                        original_context="    hikari:\n      connection-timeout: 5000\n      maximum-pool-size: 5",
                        replacement_text="    hikari:\n      connection-timeout: 30000\n      maximum-pool-size: 20"
                    )
                ],
                pre_checks=[],
                post_checks=[
                    "grep 'connection-timeout: 30000' src/main/resources/application.yml",
                    "mvn validate -pl payment-service"
                ]
            ),
            rollback=RollbackPlan(
                commands=["git revert HEAD --no-edit"],
                automatic_rollback_if=["error_rate > 5%"],
                rollback_time_seconds=60
            ),
            reasoning="Pool config was changed in last commit, reverting to previous values should restore service.",
            side_effects=["May require pod restart"],
            ai_confidence=0.93,
            similar_cases=[
                SimilarCase(
                    incident_id="inc_20260110_183045",
                    similarity=0.91,
                    fix_applied="Reverted maxPoolSize",
                    outcome="resolved",
                    resolution_time_minutes=8
                )
            ]
        ),
        Recommendation(
            rank=2,
            title="Remove hardcoded timeout in DatabaseConfig.java",
            description="Java config overrides YAML — remove hardcoded values so YAML is the source of truth",
            fix_type="local_file_edit",
            estimated_effort="low",
            estimated_time_minutes=10,
            risk_level="low",
            cost_impact="none",
            implementation=ImplementationDetails(
                type="local_file_edit",
                commands=[],
                file_edits=[
                    FileEdit(
                        file_path="src/main/java/com/acme/payment/config/DatabaseConfig.java",
                        original_context="        config.setConnectionTimeout(5000);\n        config.setMaximumPoolSize(5);",
                        replacement_text="        // timeout and pool size configured via application.yml"
                    )
                ],
                pre_checks=[],
                post_checks=["mvn compile -pl payment-service"]
            ),
            rollback=RollbackPlan(
                commands=["git checkout HEAD -- src/main/java/com/acme/payment/config/DatabaseConfig.java"],
                automatic_rollback_if=[],
                rollback_time_seconds=30
            ),
            reasoning="Java config hardcode overrides YAML, removing it makes YAML the single source of truth.",
            side_effects=[],
            ai_confidence=0.87,
            similar_cases=[]
        )
    ],
    confidence_assessment=ConfidenceAssessment(
        final_confidence=0.93,
        action="manual_review",
        threshold_used=0.85,
        risk_level="low",
        breakdown={"pattern_match": 0.95, "git_correlation": 0.91},
        adjustments={"penalties": [], "bonuses": ["git_context_available"]},
        reasoning="High confidence due to direct git correlation with config change",
        decision_factors={}
    ),
    requires_human_review=True,
    auto_heal_candidate=False,
    metadata={"model_used": "groq/llama-3.3-70b", "rag_incidents_used": 1},
    processing_time_ms=1840.0
)

# ── Run ResponseMapper ────────────────────────────────────────────────────────
print("=" * 60)
print("RUNNING ResponseMapper.map(recommendation, bundle)")
print("=" * 60)

response = ResponseMapper.map(recommendation, bundle)
output = response.model_dump()
print(json.dumps(output, indent=2))

# ── Validate shape ────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("VALIDATING OUTPUT SHAPE")
print("=" * 60)

checks = [
    ("incident_id",                lambda d: bool(d.get("incident_id"))),
    ("analyzed_at",                lambda d: bool(d.get("analyzed_at"))),
    ("processing_time_ms",         lambda d: d.get("processing_time_ms") == 1840.0),
    ("status == pending_approval", lambda d: d.get("status") == "pending_approval"),
    ("diagnosis.summary",          lambda d: bool(d["diagnosis"]["summary"])),
    ("diagnosis.root_cause",       lambda d: "HikariCP" in d["diagnosis"]["root_cause"]),
    ("diagnosis.severity",         lambda d: d["diagnosis"]["severity"] in ("critical","high","medium","low")),
    ("diagnosis.affected_services",lambda d: d["diagnosis"]["affected_services"] == ["payment-service"]),
    ("diagnosis.affected_files",   lambda d: "application.yml" in d["diagnosis"]["affected_files"][0]),
    ("diagnosis.causal_chain",     lambda d: len(d["diagnosis"]["causal_chain"]) == 3),
    ("fixes count == 2",           lambda d: len(d["fixes"]) == 2),
    ("fix_001 has file_edits",     lambda d: len(d["fixes"][0]["file_edits"]) == 1),
    ("fix_001 file = yml",         lambda d: "application.yml" in d["fixes"][0]["file_edits"][0]["file"]),
    ("fix_001 find present",       lambda d: "connection-timeout: 5000" in d["fixes"][0]["file_edits"][0]["find"]),
    ("fix_001 replace present",    lambda d: "connection-timeout: 30000" in d["fixes"][0]["file_edits"][0]["replace"]),
    ("fix_001 verify present",     lambda d: len(d["fixes"][0]["verify"]) == 2),
    ("fix_001 rollback present",   lambda d: "git revert" in d["fixes"][0]["rollback"]),
    ("fix_002 has file_edits",     lambda d: len(d["fixes"][1]["file_edits"]) == 1),
    ("fix_002 rollback present",   lambda d: "git checkout" in d["fixes"][1]["rollback"]),
    ("confidence == 0.93",         lambda d: d.get("confidence") == 0.93),
    ("approval_required == True",  lambda d: d.get("approval_required") is True),
    ("auto_applied == False",      lambda d: d.get("auto_applied") is False),
    ("_meta key present",          lambda d: "_meta" in d),
    ("_meta.model_used",           lambda d: d["_meta"]["model_used"] == "groq/llama-3.3-70b"),
    ("_meta.rag_incidents_used",   lambda d: d["_meta"]["rag_incidents_used"] == 1),
    ("_meta.similar_cases",        lambda d: "inc_20260110_183045" in d["_meta"]["similar_cases"]),
]

passed = 0
for label, check in checks:
    try:
        ok = check(output)
        print(f"  {'✅' if ok else '❌'} {label}")
        if ok: passed += 1
    except Exception as e:
        print(f"  ❌ {label} — ERROR: {e}")

print(f"\n{passed}/{len(checks)} checks passed")
if passed == len(checks):
    print("🎉 FULL END-TO-END VALIDATION PASSED")
else:
    print("⚠️  Some checks failed — review output above")
