"""
Context Module

Defines the Context for Safety Evaluation.
The Safety Matrix uses these Enums to determine legality of actions.
"""

from enum import Enum
from dataclasses import dataclass

class Environment(Enum):
    DEV = "DEV"
    PROD = "PROD"
    UNKNOWN = "UNKNOWN"

class Scope(Enum):
    SOURCE_CODE = "SOURCE_CODE" # Code changes
    INFRA = "INFRA"             # Kubernetes resources, Cloud resources
    CONFIG = "CONFIG"           # ConfigMaps, Env Vars
    UNKNOWN = "UNKNOWN"

class ExecutionMode(Enum):
    AUTO_PR = "AUTO_PR"         # Open a Pull Request
    DIRECT_APPLY = "DIRECT_APPLY" # Run command / Apply patch directly

class SafetyLevel(Enum):
    SAFE = "SAFE"                 # Can run without approval if confidence is high
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL" # Always requires HITL
    BLOCKED = "BLOCKED"           # Never allowed

@dataclass
class SafetyContext:
    environment: Environment
    scope: Scope
    execution_mode: ExecutionMode
