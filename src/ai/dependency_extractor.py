"""
Dependency Extractor Module

Auto-extracts service dependency graph from:
1. Stack traces (call chain order) - Supports Java, Python, Node.js, Go, Ruby, .NET
2. Log patterns (service/class names)
3. Causation keywords ("caused by", "failed to call", etc.)
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from src.common.types import LogPattern


@dataclass
class ExtractedDependency:
    """A discovered dependency relationship"""
    caller: str
    callee: str
    evidence: str  # The log/trace that proves this relationship
    confidence: float  # 0.0-1.0


@dataclass
class DependencyGraph:
    """Auto-extracted dependency graph"""
    nodes: List[str]  # Services in dependency order (deepest first)
    edges: List[ExtractedDependency]
    root_service: Optional[str] = None  # The entry point service


class DependencyExtractor:
    """
    Extracts service dependencies from logs and stack traces.
    
    Supports multiple tech stacks:
    - Java (Spring Boot, etc.)
    - Python (Django, Flask, FastAPI)
    - Node.js (Express, NestJS)
    - Go (Gin, Fiber, standard library)
    - Ruby (Rails)
    - .NET (ASP.NET Core)
    """
    
    # =========================================================================
    # MULTI-STACK TRACE PATTERNS
    # =========================================================================
    
    # Java: at com.example.Service.method(Service.java:45)
    JAVA_STACK_PATTERN = re.compile(
        r'at\s+([\w.$]+)\.([\w$<>]+)\(([^)]+)\)',
        re.MULTILINE
    )
    
    # Python: File "/path/to/file.py", line 45, in function_name
    PYTHON_STACK_PATTERN = re.compile(
        r'File\s+"([^"]+)",\s+line\s+\d+,\s+in\s+([\w_]+)',
        re.MULTILINE
    )
    
    # Node.js: at FunctionName (/path/to/file.js:45:12)
    NODEJS_STACK_PATTERN = re.compile(
        r'at\s+([\w.]+)?\s*\(?([^:]+\.(?:js|ts)):(\d+):(\d+)\)?',
        re.MULTILINE
    )
    
    # Go: /path/to/file.go:45 +0x123
    GO_STACK_PATTERN = re.compile(
        r'([\w/]+\.go):(\d+)',
        re.MULTILINE
    )
    
    # Ruby: from /path/to/file.rb:45:in `method_name'
    RUBY_STACK_PATTERN = re.compile(
        r"from\s+([^:]+\.rb):(\d+):in\s+`([^']+)'",
        re.MULTILINE
    )
    
    # .NET: at Namespace.Class.Method() in /path/file.cs:line 45
    DOTNET_STACK_PATTERN = re.compile(
        r'at\s+([\w.]+)\.([\w<>]+)\(.*?\)(?:\s+in\s+([^:]+))?',
        re.MULTILINE
    )
    
    # Pattern for "Caused by" chains (all stacks)
    CAUSED_BY_PATTERN = re.compile(
        r'Caused\s+by:\s*([\w.]+Exception|[\w.]+Error)',
        re.IGNORECASE
    )
    
    # Common service/component indicators (stack-agnostic)
    SERVICE_INDICATORS = [
        # Generic
        'service', 'controller', 'repository', 'handler', 'manager', 'provider',
        'client', 'adapter', 'gateway', 'processor', 'worker', 'job',
        # Python
        'view', 'viewset', 'serializer', 'model', 'task', 'celery',
        # Node.js
        'router', 'middleware', 'resolver',
        # Go
        'server', 'grpc',
        # Ruby
        'mailer', 'concern',
    ]
    
    # Known infrastructure components (ordered by depth - deepest first)
    # Stack-agnostic ordering
    INFRA_DEPTH_ORDER = [
        # Data stores (deepest - all stacks)
        'mysql', 'postgres', 'pg', 'mongodb', 'mongo', 'redis', 'memcached',
        'kafka', 'rabbitmq', 'amqp', 'elasticsearch', 'sqlite', 'dynamodb', 's3',
        # Connection pools (all stacks)
        'hikari', 'pool', 'connection', 'datasource', 'client', 'driver',
        'sqlalchemy', 'sequelize', 'prisma', 'typeorm', 'gorm', 'activerecord',
        # ORM/Data layer
        'hibernate', 'jpa', 'repository', 'model', 'entity', 'dao', 'mapper',
        # Business/Service layer
        'service', 'usecase', 'interactor', 'domain',
        # API/Controller layer
        'controller', 'handler', 'resolver', 'view', 'endpoint', 'route', 'router',
        # Web server layer
        'tomcat', 'jetty', 'netty', 'express', 'fastify', 'koa', 'gin', 'fiber',
        'flask', 'django', 'fastapi', 'uvicorn', 'gunicorn', 'puma', 'unicorn',
        # Framework layer (shallowest)
        'spring', 'rails', 'laravel', 'nest', 'application', 'app', 'main',
    ]
    
    @classmethod
    def extract_from_patterns(
        cls,
        patterns: List[LogPattern],
        events: Optional[List] = None,
        metrics: Optional[Dict] = None
    ) -> DependencyGraph:
        """
        Main entry point: Extract dependency graph from logs, events, and metrics.
        
        Args:
            patterns: Log patterns with stack traces
            events: K8s/system events with service names
            metrics: Anomaly metrics (may contain service labels)
        
        Returns ordered list with deepest dependencies first.
        """
        all_services: Set[str] = set()
        edges: List[ExtractedDependency] = []
        call_chains: List[List[str]] = []
        
        # =====================================================================
        # STRATEGY 1: Extract from Log Patterns (stack traces)
        # =====================================================================
        for pattern in patterns:
            text = pattern.pattern
            
            # Parse stack traces (multi-stack)
            chain = cls._extract_stack_trace_chain(text)
            if chain:
                call_chains.append(chain)
                all_services.update(chain)
            
            # Extract service names from log text
            services = cls._extract_service_names(text)
            all_services.update(services)
            
            # Find "Caused by" relationships
            caused_by = cls._extract_caused_by_chain(text)
            if caused_by:
                for i in range(len(caused_by) - 1):
                    edges.append(ExtractedDependency(
                        caller=caused_by[i],
                        callee=caused_by[i + 1],
                        evidence=text[:100],
                        confidence=0.8
                    ))
                all_services.update(caused_by)
        
        # =====================================================================
        # STRATEGY 2: Extract from Events
        # =====================================================================
        if events:
            event_services, event_edges = cls._extract_from_events(events)
            all_services.update(event_services)
            edges.extend(event_edges)
        
        # =====================================================================
        # STRATEGY 3: Extract from Metrics (service labels)
        # =====================================================================
        if metrics:
            metric_services = cls._extract_from_metrics(metrics)
            all_services.update(metric_services)
        
        # Build ordered dependency list
        ordered = cls._order_by_depth(list(all_services), call_chains, edges)
        
        # Identify root service (typically the application entry point)
        root = cls._identify_root_service(ordered, call_chains)
        
        return DependencyGraph(
            nodes=ordered,
            edges=edges,
            root_service=root
        )
    
    @classmethod
    def _extract_from_events(cls, events: List) -> Tuple[Set[str], List[ExtractedDependency]]:
        """
        Extract service names and relationships from events.
        
        Looks for:
        - event.service field
        - Patterns like "calling X failed" in reason
        - Pod names that indicate services
        """
        services: Set[str] = set()
        edges: List[ExtractedDependency] = []
        
        for event in events:
            # Extract service field
            if hasattr(event, 'service') and event.service:
                services.add(event.service)
            elif isinstance(event, dict) and event.get('service'):
                services.add(event['service'])
            
            # Extract from reason text
            reason = getattr(event, 'reason', None) or (event.get('reason') if isinstance(event, dict) else '')
            if reason:
                # Pattern: "calling user-service failed"
                call_match = re.search(r'(?:calling|connecting to|request to)\s+([a-zA-Z][\w-]+)', reason, re.IGNORECASE)
                if call_match:
                    target_service = call_match.group(1)
                    services.add(target_service)
                    
                    # Create edge if we have source service
                    source = getattr(event, 'service', None) or (event.get('service') if isinstance(event, dict) else None)
                    if source:
                        edges.append(ExtractedDependency(
                            caller=source,
                            callee=target_service,
                            evidence=reason[:100],
                            confidence=0.9
                        ))
                
                # Extract any service-like names from reason
                service_names = cls._extract_service_names(reason)
                services.update(service_names)
            
            # Extract from pod name (e.g., "payment-service-abc123")
            pod = getattr(event, 'pod', None) or (event.get('pod') if isinstance(event, dict) else '')
            if pod:
                # Strip kubernetes suffixes
                pod_clean = re.sub(r'-[a-f0-9]+-[a-z0-9]+$', '', pod)
                pod_clean = re.sub(r'-\d+$', '', pod_clean)
                if pod_clean and len(pod_clean) > 2:
                    services.add(pod_clean)
        
        return services, edges
    
    @classmethod
    def _extract_from_metrics(cls, metrics) -> Set[str]:
        """
        Extract service names from metric labels.
        
        Metrics often have labels like:
        - service_name
        - container_name
        - deployment_name
        """
        services: Set[str] = set()
        
        if isinstance(metrics, dict):
            # Look for service-related keys
            for key in ['service', 'service_name', 'container', 'deployment', 'pod']:
                if key in metrics and isinstance(metrics[key], str):
                    services.add(metrics[key])
        
        return services
    
    @classmethod
    def _extract_stack_trace_chain(cls, text: str) -> List[str]:
        """
        Extract call chain from stack trace (multi-stack support).
        
        Supports: Java, Python, Node.js, Go, Ruby, .NET
        """
        chain = []
        seen = set()
        
        # Try Java pattern
        java_matches = cls.JAVA_STACK_PATTERN.findall(text)
        for full_class, method, location in java_matches:
            class_name = full_class.split('.')[-1]
            if not cls._is_framework_class(full_class) and class_name not in seen:
                seen.add(class_name)
                chain.append(class_name)
        
        # Try Python pattern
        py_matches = cls.PYTHON_STACK_PATTERN.findall(text)
        for file_path, func_name in py_matches:
            # Extract module name from path
            module = file_path.split('/')[-1].replace('.py', '')
            if not cls._is_framework_path(file_path) and module not in seen:
                seen.add(module)
                chain.append(module)
        
        # Try Node.js pattern
        node_matches = cls.NODEJS_STACK_PATTERN.findall(text)
        for func_name, file_path, line, col in node_matches:
            name = func_name if func_name else file_path.split('/')[-1].replace('.js', '').replace('.ts', '')
            if not cls._is_framework_path(file_path) and name not in seen:
                seen.add(name)
                chain.append(name)
        
        # Try Go pattern  
        go_matches = cls.GO_STACK_PATTERN.findall(text)
        for file_path, line in go_matches:
            module = file_path.split('/')[-1].replace('.go', '')
            if not cls._is_framework_path(file_path) and module not in seen:
                seen.add(module)
                chain.append(module)
        
        # Try Ruby pattern
        ruby_matches = cls.RUBY_STACK_PATTERN.findall(text)
        for file_path, line, method in ruby_matches:
            module = file_path.split('/')[-1].replace('.rb', '')
            if not cls._is_framework_path(file_path) and module not in seen:
                seen.add(module)
                chain.append(module)
        
        # Try .NET pattern
        dotnet_matches = cls.DOTNET_STACK_PATTERN.findall(text)
        for namespace_class, method, file_path in dotnet_matches:
            class_name = namespace_class.split('.')[-1]
            if not cls._is_framework_class(namespace_class) and class_name not in seen:
                seen.add(class_name)
                chain.append(class_name)
        
        return chain
    
    @classmethod
    def _extract_service_names(cls, text: str) -> List[str]:
        """
        Extract service/component names from log text (multi-stack).
        """
        services = []
        
        # Pattern 1: CamelCase class names (Java, .NET, Node)
        camel_case = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', text)
        services.extend(camel_case)
        
        # Pattern 2: snake_case modules (Python, Ruby, Go)
        snake_case = re.findall(r'\b([a-z][a-z0-9]*_[a-z][a-z0-9_]*)\b', text)
        services.extend([s for s in snake_case if len(s) > 4])
        
        # Pattern 3: Bracketed service names [service-name]
        bracketed = re.findall(r'\[([\w-]+)\]', text)
        services.extend(bracketed)
        
        # Pattern 4: Service/component suffixes (all stacks)
        for suffix in ['Service', 'Controller', 'Handler', 'Pool', 'Client', 'Repository', 
                       'Model', 'View', 'Router', 'Worker', 'Job', 'Task']:
            pattern_matches = re.findall(rf'([\w]+{suffix})', text)
            services.extend(pattern_matches)
        
        # Pattern 5: Docker/K8s container names
        container_names = re.findall(r'container[_-]?(?:name)?[=:]\s*["\']?([\w-]+)', text, re.IGNORECASE)
        services.extend(container_names)
        
        return list(set(services))
    
    @classmethod
    def _extract_caused_by_chain(cls, text: str) -> List[str]:
        """
        Extract exception chain from "Caused by" patterns.
        
        Returns list of exception/service names in causal order.
        """
        matches = cls.CAUSED_BY_PATTERN.findall(text)
        if not matches:
            return []
        
        # Extract service name from exception (e.g., "SQLException" → "SQL")
        chain = []
        for exc in matches:
            service = exc.replace('Exception', '').replace('Error', '')
            service = service.split('.')[-1]  # Get simple name
            if service and len(service) > 2:
                chain.append(service)
        
        return chain
    
    @classmethod
    def _order_by_depth(
        cls,
        services: List[str],
        call_chains: List[List[str]],
        edges: List[ExtractedDependency]
    ) -> List[str]:
        """
        Order services by dependency depth (deepest first).
        """
        depth_scores: Dict[str, int] = defaultdict(int)
        
        # Score by known infra depth
        for service in services:
            service_lower = service.lower()
            for i, indicator in enumerate(cls.INFRA_DEPTH_ORDER):
                if indicator in service_lower:
                    # Higher index = shallower, so we invert
                    depth_scores[service] = max(
                        depth_scores[service],
                        len(cls.INFRA_DEPTH_ORDER) - i
                    )
                    break
        
        # Score by call chain position (later in chain = deeper)
        for chain in call_chains:
            for i, service in enumerate(chain):
                # Later position = deeper dependency
                depth_scores[service] = max(depth_scores[service], i + 1)
        
        # Sort by depth score (descending)
        ordered = sorted(services, key=lambda s: depth_scores.get(s, 0), reverse=True)
        
        return ordered
    
    @classmethod
    def _identify_root_service(
        cls,
        ordered_services: List[str],
        call_chains: List[List[str]]
    ) -> Optional[str]:
        """Identify the application entry point service"""
        # Look for Application/App class
        for svc in ordered_services:
            if 'application' in svc.lower() or svc.lower() == 'app' or svc.lower() == 'main':
                return svc
        
        # Otherwise, the shallowest in call chains
        if ordered_services:
            return ordered_services[-1]  # Last = shallowest
        
        return None
    
    @classmethod
    def _is_framework_class(cls, full_class: str) -> bool:
        """Check if this is a framework class we should skip (multi-stack)"""
        framework_prefixes = [
            # Java
            'java.', 'javax.', 'sun.', 'jdk.',
            'org.springframework.', 'org.apache.', 'org.hibernate.', 'com.zaxxer.',
            'reactor.', 'io.netty.',
            # .NET
            'System.', 'Microsoft.', 'mscorlib.',
            # Node.js paths
            'node_modules', 'internal/',
        ]
        return any(p in full_class for p in framework_prefixes)
    
    @classmethod
    def _is_framework_path(cls, path: str) -> bool:
        """Check if this is a framework file path we should skip"""
        framework_paths = [
            # Python
            'site-packages', 'dist-packages', '/usr/lib/python', 'importlib',
            'django/core', 'flask/', 'fastapi/', 'starlette/', 'uvicorn/',
            # Node.js
            'node_modules/', 'internal/', '<anonymous>',
            # Ruby  
            '/gems/', 'bundler/', 'rubygems/',
            # Go
            '/pkg/mod/', 'runtime/',
        ]
        return any(p in path for p in framework_paths)
