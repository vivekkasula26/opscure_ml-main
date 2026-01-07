"""
Tool Catalog Module

Registry for all available remediation tools.
Allows dynamic discovery and safety checks.
"""

from typing import Dict, Callable, Optional, List
from dataclasses import dataclass
from src.remediation.safety import SafetyLevel

@dataclass
class ToolMetadata:
    name: str
    description: str
    safety_level: SafetyLevel
    requires_arguments: bool
    
class ToolRegistry:
    """
    Central registry for remediation tools.
    """
    _tools: Dict[str, ToolMetadata] = {}
    _handlers: Dict[str, Callable] = {}
    
    @classmethod
    def register(cls, name: str, description: str, safety_level: SafetyLevel, requires_arguments: bool = True):
        """
        Decorator to register a function as a tool.
        """
        def decorator(func: Callable):
            cls._tools[name] = ToolMetadata(
                name=name,
                description=description,
                safety_level=safety_level,
                requires_arguments=requires_arguments
            )
            cls._handlers[name] = func
            return func
        return decorator

    @classmethod
    def get_tool(cls, name: str) -> Optional[Callable]:
        return cls._handlers.get(name)
    
    @classmethod
    def get_metadata(cls, name: str) -> Optional[ToolMetadata]:
        return cls._tools.get(name)
        
    @classmethod
    def list_tools(cls) -> List[ToolMetadata]:
        return list(cls._tools.values())
