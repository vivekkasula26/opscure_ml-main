"""
Safety Policy Module

Enforces boundaries on what the Agent can and cannot do.
Classifies commands into SafetyLevels.
"""

from enum import Enum
from typing import List, Dict, Set, Optional
import re
from src.remediation.context import SafetyContext, Environment, Scope, ExecutionMode, SafetyLevel
from src.remediation.config import SafetyConfiguration, ConfigLoader

class SafetyPolicy:
    """
    Evaluating the safety of proposed actions.
    """
    
    # Whitelists for SAFE commands (Read-only or low risk)
    SAFE_COMMANDS: Set[str] = {
        "ls", "grep", "cat", "echo", "pwd", 
        "kubectl get", "kubectl describe", "kubectl logs",
        "git status", "git log", "git diff"
    }

    # Commands that are useful but dangerous (Require Approval)
    APPROVAL_REQUIRED_COMMANDS: Set[str] = {
        "kubectl delete", "kubectl scale", "kubectl patch", "kubectl apply",
        "rm", "mv", "cp", "touch", "mkdir",
        "git commit", "git push", "git merge",
        "systemctl restart", "docker stop", "docker restart"
    }

    # Strictly forbidden
    BLOCKED_PATTERNS: List[str] = [
        r"rm -rf /$", r"rm -rf /\*", # Nuke root
        r">\s*/etc/",                # Overwrite system config
        r"chmod 777",                # Permissive permissions
        r"mkfs", "dd ",              # Disk formatting
        r":(){ :|:& };:"             # Fork bomb
    ]
    
    _config: SafetyConfiguration = SafetyConfiguration()

    @classmethod
    def load_config(cls, path: str = None):
        if path:
            cls._config = ConfigLoader.load(path)
        else:
            cls._config = ConfigLoader.load()

    @staticmethod
    def evaluate_matrix(context: SafetyContext) -> SafetyLevel:
        """
        Layer 1: The Safety Matrix (Hard Guardrails)
        Evaluates based on Facts: Scope, Environment, Execution Mode.
        """
        # User Overrides first
        # Very simple matching for MVP
        for rule in SafetyPolicy._config.matrix_overrides:
            match_env = rule.get("environment") == context.environment.value
            match_scope = rule.get("scope") == context.scope.value
            if match_env and match_scope:
                # Enforce user override
                level_str = rule.get("level", "REQUIRE_APPROVAL")
                return SafetyLevel(level_str)
        
        # Rule 1: Source Code
        if context.scope == Scope.SOURCE_CODE:
            if context.execution_mode == ExecutionMode.DIRECT_APPLY:
                return SafetyLevel.BLOCKED  # FORBIDDEN: Never directly mutate source code
            if context.execution_mode == ExecutionMode.AUTO_PR:
                return SafetyLevel.REQUIRE_APPROVAL # HITL: PR requires review
                
        # Rule 2: Infrastructure
        if context.scope == Scope.INFRA:
            if context.environment == Environment.PROD:
                if context.execution_mode == ExecutionMode.DIRECT_APPLY:
                    return SafetyLevel.REQUIRE_APPROVAL # HITL: Prod infra changes are too risky
            if context.environment == Environment.DEV:
                if context.execution_mode == ExecutionMode.DIRECT_APPLY:
                    return SafetyLevel.SAFE # Safe for Auto-Heal in Dev
                    
        # Rule 3: Config
        if context.scope == Scope.CONFIG:
             return SafetyLevel.REQUIRE_APPROVAL # Default to HITL for config changes
             
        # Default safety net
        return SafetyLevel.REQUIRE_APPROVAL

    @staticmethod
    def evaluate_command(command_str: str, context: Optional[SafetyContext] = None) -> SafetyLevel:
        """
        Determines the safety level of a shell command string.
        Now also considers the Safety Matrix if context is provided.
        """
        command_str = command_str.strip()
        
        # 0. User Blocklist (Takes precedence over EVERYTHING)
        for pattern in SafetyPolicy._config.custom_blocked_patterns:
            if re.search(pattern, command_str):
                 return SafetyLevel.BLOCKED

        # 1. Check System Blocklist
        for pattern in SafetyPolicy.BLOCKED_PATTERNS:
            if re.search(pattern, command_str):
                return SafetyLevel.BLOCKED
        
        # 1.5 User Whitelist (Trust user implicitly for specific commands)
        # Check this BEFORE matrix? Or AFTER?
        # Typically whitelist implies "I know what I'm doing".
        # But Matrix (Environment) usually trumps Command safety.
        # Let's stick to: Matrix rules first (Environment Safety), then Command Safety.
        # UNLESS the user explicitly allowed it? 
        # For safety, let's say Matrix applies to *Context*. Command Whitelist applies to *Tool*.
        # So we check Matrix first (Layer 1).
        
        # 2. If Context is provided, check the Matrix (Layer 1)
        if context:
            matrix_decision = SafetyPolicy.evaluate_matrix(context)
            if matrix_decision == SafetyLevel.BLOCKED:
                return SafetyLevel.BLOCKED
            
            if matrix_decision == SafetyLevel.REQUIRE_APPROVAL:
                return SafetyLevel.REQUIRE_APPROVAL
        
        # 3. User Whitelist (Now safe to check)
        # If user explicitly whitelisted this command string, it is SAFE.
        # Simple exact match or base command match?
        base_cmd = command_str.split()[0]
        if base_cmd in SafetyPolicy._config.custom_allowed_commands:
             return SafetyLevel.SAFE

        # 4. Check System Whitelist
        if base_cmd in SafetyPolicy.SAFE_COMMANDS:
            # Need to ensure no dangerous flags like ">" are used in safe commands if we want true safety
            # For now, simplistic check
            if ">" in command_str or "|" in command_str: 
                 # Pipelines/Redirects increase risk
                 return SafetyLevel.REQUIRE_APPROVAL
            return SafetyLevel.SAFE
            
        # 4. Check Approval List
        # Check if the base command is in the approval list
        # We need to handle 'kubectl delete' vs just 'kubectl'
        # Let's check pure base first
        simple_base = command_str.split()[0]
        if simple_base in SafetyPolicy.APPROVAL_REQUIRED_COMMANDS:
             return SafetyLevel.REQUIRE_APPROVAL
        
        # Check composite for kubectl
        if base_cmd in SafetyPolicy.APPROVAL_REQUIRED_COMMANDS:
             return SafetyLevel.REQUIRE_APPROVAL

        # Default to BLOCKED/APPROVAL? 
        # Unknown commands should be treated with caution.
        return SafetyLevel.REQUIRE_APPROVAL
