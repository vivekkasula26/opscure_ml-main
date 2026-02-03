"""
Ingestion Module

Provides log parsing and CorrelationBundle creation.
"""

from .log_parser import LogParserService, get_log_parser_service

__all__ = ['LogParserService', 'get_log_parser_service']
