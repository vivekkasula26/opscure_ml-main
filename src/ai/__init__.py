"""
AI Pipeline Module for Opscure
CorrelationBundle → AIRecommendation pipeline
"""

from .summarizer import Summarizer
from .pinecone_client import PineconeClient, get_pinecone_client
from .prompt_builder import PromptBuilder
from .ollama_client import OllamaClient, get_ollama_client
from .ai_output_parser import AIOutputParser
from .ai_adapter_service import AIAdapterService, get_ai_adapter_service

__all__ = [
    "Summarizer",
    "PineconeClient",
    "get_pinecone_client",
    "PromptBuilder",
    "OllamaClient",
    "get_ollama_client",
    "AIOutputParser",
    "AIAdapterService",
    "get_ai_adapter_service",
]

