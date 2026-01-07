"""
User Config Verification

Tests that user-defined rules in opscure_safety.json override system defaults.
"""

import sys
import os
import json
from unittest.mock import MagicMock

# Mock sys.modules
sys.modules["aiohttp"] = MagicMock()

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.remediation.config import SafetyConfiguration
from src.remediation.safety import SafetyPolicy, SafetyLevel
from src.remediation.context import SafetyContext, Environment, Scope, ExecutionMode

CONFIG_FILE = "opscure_safety.json"

def write_test_config():
    data = {
        "allowed_commands": ["my_custom_tool"],
        "blocked_patterns": ["grep"],  # Crazy user wants to block grep
        "matrix_overrides": [
            {
                "environment": "DEV",
                "scope": "INFRA",
                "level": "REQUIRE_APPROVAL" # Overriding Default SAFE
            }
        ]
    }
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

def cleanup():
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)

def run_tests():
    print("--- User Configuration Tests ---")
    
    # 1. Setup Config
    write_test_config()
    SafetyPolicy.load_config(CONFIG_FILE)
    
    # Test 1: User Blocklist overrides System Whitelist
    # 'grep' is normally SAFE. User blocked it.
    res = SafetyPolicy.evaluate_command("grep error log.txt")
    print(f"1. Blocking 'grep' (User override): {res}")
    assert res == SafetyLevel.BLOCKED
    
    # Test 2: User Whitelist adds new command
    # 'my_custom_tool' is unknown (would be Approval). User allowed it.
    res = SafetyPolicy.evaluate_command("my_custom_tool --flag")
    print(f"2. Allowing 'my_custom_tool': {res}")
    assert res == SafetyLevel.SAFE
    
    # Test 3: Matrix Override
    # Dev Infra is normally SAFE. User forced HITL.
    ctx = SafetyContext(Environment.DEV, Scope.INFRA, ExecutionMode.DIRECT_APPLY)
    res = SafetyPolicy.evaluate_matrix(ctx)
    print(f"3. Matrix Override (Dev Infra -> HITL): {res}")
    assert res == SafetyLevel.REQUIRE_APPROVAL
    
    cleanup()
    print("\nALL CONFIG CHECKS PASSED")

if __name__ == "__main__":
    try:
        run_tests()
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        cleanup()
    except Exception as e:
        print(f"\nERROR: {e}")
        cleanup()
