"""
AI Adapter Service
Core orchestration component for the AI pipeline.

Flow:
1. Receive CorrelationBundle
2. Build textual summary for embedding
3. Query Pinecone for similar incident context
4. Build prompt via PromptBuilder
5. Call OllamaClient with fallback logic
6. Parse model output as JSON
7. Wrap into AIRecommendation
"""


import os
from typing import Optional, Union
from datetime import datetime

from src.common.types import CorrelationBundle, AIRecommendation, create_degraded_recommendation
from src.ai.summarizer import Summarizer
from src.ai.pinecone_client import PineconeClient, get_pinecone_client
from src.ai.prompt_builder import PromptBuilder

from src.ai.ollama_client import OllamaClient, get_ollama_client
from src.ai.groq_client import GroqClient, get_groq_client
from src.ai.ai_output_parser import AIOutputParser
from src.ai.agent import RemediationAgent, AgentResult
from src.remediation.types import RemediationProposal


class AIAdapterService:
    """
    Core service that orchestrates the AI pipeline.
    
    Takes a CorrelationBundle and produces an AIRecommendation
    by coordinating:
    - Summarizer (for embedding text)
    - PineconeClient (for RAG retrieval)
    - PromptBuilder (for prompt construction)
    - OllamaClient (for AI inference)
    - AIOutputParser (for response parsing)
    """
    
    def __init__(
        self,
        pinecone_client: Optional[PineconeClient] = None,
        llm_client: Optional[Union[OllamaClient, GroqClient]] = None
    ):
        """
        Initialize AI Adapter Service.
        
        Args:
            pinecone_client: Optional Pinecone client (uses singleton if not provided)
            llm_client: Optional LLM client (uses singleton if not provided)
        """
        self._pinecone_client = pinecone_client
        
        # Default to Ollama if not provided, logic handled in factory normally
        if llm_client:
            self._llm_client = llm_client
        else:
            # Fallback for direct instantiation without factory
            provider = os.getenv("LLM_PROVIDER", "ollama")
            print(f"[AIAdapterService] Using LLM Provider: {provider}")
            self._llm_client = get_groq_client()
         
        
        # Metrics tracking
        self.metrics = {
            "total_requests": 0,
            "successful": 0,
            "degraded": 0,
            "avg_latency_ms": 0
        }
        
        # Remediation Agent
        self._remediation_agent = RemediationAgent()
    
    async def _get_pinecone_client(self) -> PineconeClient:
        """Get Pinecone client, initializing if needed"""
        if self._pinecone_client is None:
            self._pinecone_client = await get_pinecone_client()
        return self._pinecone_client
    
    async def create_ai_recommendation(
        self,
        bundle: CorrelationBundle,
        use_rag: bool = True,
        top_k: int = 5
    ) -> AIRecommendation:
        """
        Create an AI recommendation from a CorrelationBundle.
        
        This is the main entry point for the AI pipeline.
        
        Args:
            bundle: The correlation bundle to analyze
            use_rag: Whether to use RAG for similar incident context
            top_k: Number of similar incidents to retrieve
            
        Returns:
            AIRecommendation with root cause, causal chain, and fix plan
        """
        start_time = datetime.utcnow()
        self.metrics["total_requests"] += 1
        
        print(f"[AIAdapterService] Processing bundle: {bundle.id}")
        
        try:
            # Step 1: Build textual summary for embedding
            summary = Summarizer.summarize_bundle(bundle)
            print(f"[AIAdapterService] Summary length: {len(summary)} chars")
            
            # Step 2: Query Pinecone for similar incidents (if RAG enabled)
            similar_incidents = []
            if use_rag:
                pinecone = await self._get_pinecone_client()
                embedding = pinecone.embed(summary)
                similar_incidents = await pinecone.query_similar_incidents(embedding, top_k)
                print(f"[AIAdapterService] Retrieved {len(similar_incidents)} similar incidents")
            
            # Step 3: Build prompt
            prompt = PromptBuilder.build_prompt(bundle, similar_incidents)
            system_prompt = PromptBuilder.SYSTEM_PROMPT
            print(f"[AIAdapterService] Prompt length: {len(prompt)} chars")
            
            # Step 4: Call LLM with fallback logic
            raw_output, model_used = await self._llm_client.generate_with_fallback(
                prompt=prompt,
                system_prompt=system_prompt
            )
            print(f"[AIAdapterService] Model used: {model_used}")
            
            # Step 5: Parse model output
            recommendation = AIOutputParser.parse(raw_output, bundle.id)
            
            # Validate the recommendation
            issues = AIOutputParser.validate_recommendation(recommendation)
            if issues:
                print(f"[AIAdapterService] Validation issues: {issues}")
            
            # Track metrics
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._update_metrics(latency_ms, model_used != "degraded")
            
            print(f"[AIAdapterService] Completed in {latency_ms:.0f}ms, confidence: {recommendation.confidence_assessment.final_confidence}")
            
            return recommendation
            
        except Exception as e:
            print(f"[AIAdapterService] Error processing bundle: {e}")
            self.metrics["degraded"] += 1
            return create_degraded_recommendation(bundle.id)
    
    async def analyze_bundle(
        self,
        bundle: CorrelationBundle
    ) -> AIRecommendation:
        """
        Alias for create_ai_recommendation with default settings.
        
        Args:
            bundle: The correlation bundle to analyze
            
        Returns:
            AIRecommendation
        """
        return await self.create_ai_recommendation(bundle)
    
    async def analyze_without_rag(
        self,
        bundle: CorrelationBundle
    ) -> AIRecommendation:
        """
        Analyze bundle without RAG context.
        Useful for testing or when Pinecone is unavailable.
        
        Args:
            bundle: The correlation bundle to analyze
            
        Returns:
            AIRecommendation
        """
        return await self.create_ai_recommendation(bundle, use_rag=False)
        
    async def create_remediation_proposal(
        self,
        bundle: CorrelationBundle
    ) -> Optional[RemediationProposal]:
        """
        Generate a remediation proposal for the given bundle.
        
        Args:
            bundle: The correlation bundle to analyze
            
        Returns:
            RemediationProposal with Plan and Actions (or None if failed)
        """
        print(f"[AIAdapterService] Generating remediation proposal for: {bundle.id}")
        try:
            # 1. Generate Proposal via AI (Think)
            # In a real async implementation, we would await this.
            # Reuse the main recommendation flow or call a specialized prompt
            # For now, let's assume we have a bundle and want to turn it into a proposal
            
            # NOTE: Ideally we call create_ai_recommendation first, then convert to proposal.
            # But to keep this method signature valid for now:
            
            # Use the simple analysis flow
            rec = await self.create_ai_recommendation(bundle, use_rag=False)
            
            # Convert AIRecommendation -> RemediationProposal
            # This logic ideally belongs in a converter, but doing it inline for MVP
            
            if not rec.recommendations:
                return None
                
            top_rec = rec.recommendations[0]
            
            # Map valid actions
            actions = []
            if top_rec.implementation:
                # Naive mapping: assume specific command structure from AI
                # In production, we'd have a robust mapper
                import src.remediation.types as rt
                
                # Check implementation type
                action_type = rt.ActionType.COMMAND
                if top_rec.implementation.type == "git_workflow":
                    action_type = rt.ActionType.PATCH # Or new GIT_WORKFLOW type if added
                
                for cmd in top_rec.implementation.commands:
                    actions.append(rt.RemediationAction(
                        type=action_type,
                        command=cmd,
                        context="."
                    ))

            proposal = RemediationProposal(
                plan=rt.RemediationPlan(
                    title=top_rec.title,
                    reasoning=top_rec.reasoning,
                    validation_strategy="Monitor metrics",
                    risk_assessment=top_rec.risk_level
                ),
                actions=actions,
                confidence_score=rec.confidence_assessment.final_confidence
            )

            # 2. Execute via Agent (Act)
            result: AgentResult = self._remediation_agent.run(proposal)
            
            # Log the decision
            print(f"[AIAdapterService] Remediation Decision: {result.confidence_result.decision}")
            
            return result.proposal
            
        except Exception as e:
            print(f"[AIAdapterService] Error creating remediation proposal: {e}")
            return None
    
    def _update_metrics(self, latency_ms: float, success: bool):
        """Update internal metrics"""
        if success:
            self.metrics["successful"] += 1
        else:
            self.metrics["degraded"] += 1
        
        # Update rolling average latency
        total = self.metrics["total_requests"]
        current_avg = self.metrics["avg_latency_ms"]
        self.metrics["avg_latency_ms"] = (current_avg * (total - 1) + latency_ms) / total
    
    def get_metrics(self) -> dict:
        """Get service metrics"""
        return {
            **self.metrics,
            "success_rate": (
                self.metrics["successful"] / max(self.metrics["total_requests"], 1)
            )
        }
    
    async def health_check(self) -> dict:
        """
        Check health of all dependencies.
        
        Returns:
            Dict with health status of each component
        """
        health = {
            "service": "AIAdapterService",
            "status": "healthy",
            "components": {}
        }
        
        # Check LLM Provider
        llm_health = await self._llm_client.health_check()
        health["components"]["llm"] = llm_health
        
        # Check Pinecone
        try:
            pinecone = await self._get_pinecone_client()
            health["components"]["pinecone"] = {
                "status": "healthy" if pinecone._initialized else "initializing"
            }
        except Exception as e:
            health["components"]["pinecone"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Overall status
        if any(
            c.get("status") == "unhealthy"
            for c in health["components"].values()
        ):
            health["status"] = "degraded"
        
        return health
    
    async def close(self):
        """Clean up resources"""
        await self._llm_client.close()


# Singleton instance
_ai_adapter_service: Optional[AIAdapterService] = None


async def get_ai_adapter_service() -> AIAdapterService:
    """Get or create AI Adapter Service singleton"""
    global _ai_adapter_service
    
    if _ai_adapter_service is None:
        provider = os.getenv("LLM_PROVIDER", "ollama")
        client = get_groq_client()
        
            
        _ai_adapter_service = AIAdapterService(llm_client=client)
    
    return _ai_adapter_service

