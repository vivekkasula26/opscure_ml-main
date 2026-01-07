"""
Safety Configuration Module

Allows users to define custom safety rules, overriding system defaults.
"""

import json
import os
from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field

@dataclass
class SafetyConfiguration:
    """
    User-defined safety rules.
    """
    # Commands that the user explicitly trusts (Override Blocked/Approval?)
    # Generally we only allow overriding Approval -> Safe. Blocked -> Safe is dangerous.
    # Let's say these are added to the SAFE whitelist.
    custom_allowed_commands: Set[str] = field(default_factory=set)
    
    # Commands the user specifically wants to BLOCK (e.g. "helm delete")
    custom_blocked_patterns: List[str] = field(default_factory=list)
    
    # Force specific contexts to be HITL (e.g. always review Dev changes)
    # format: {"environment": "DEV", "scope": "INFRA", "level": "REQUIRE_APPROVAL"}
    matrix_overrides: List[Dict] = field(default_factory=list)

class ConfigLoader:
    """
    Loads configuration from disk.
    """
    DEFAULT_PATH = "opscure_safety.json" # defaulting to JSON for stdlib support
    
    @staticmethod
    def load(path: str = DEFAULT_PATH) -> SafetyConfiguration:
        config = SafetyConfiguration()
        
        if not os.path.exists(path):
            return config
            
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                
            config.custom_allowed_commands = set(data.get("allowed_commands", []))
            config.custom_blocked_patterns = data.get("blocked_patterns", [])
            config.matrix_overrides = data.get("matrix_overrides", [])
            
            print(f"[ConfigLoader] Loaded user safety rules from {path}")
            
        except Exception as e:
            print(f"[ConfigLoader] Failed to load config: {e}")
            
        return config
