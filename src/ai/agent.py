"""
Remediation Agent Module

Orchestrates the Sense -> Think -> Act loop.
1. Sense: Summarize the CorrelationBundle.
2. Think: Generate a RemediationProposal (via LLM) and Evaluate it (Confidence Engine).
3. Act: Execute the action (if Safe) or Request Approval.
"""

from typing import Optional, List
from dataclasses import dataclass

from src.common.types import CorrelationBundle
from src.common.types import CorrelationBundle
from src.ai.summarizer import Summarizer
from src.ai.pinecone_client import get_pinecone_client
from src.ai.ai_output_parser import AIOutputParser
from src.remediation.types import RemediationProposal, RemediationAction, ActionType
from src.remediation.confidence import ConfidenceScorer, ConfidenceResult, FeedbackStore
from src.remediation.safety import SafetyLevel, SafetyPolicy


@dataclass
class AgentResult:
    proposal: RemediationProposal
    confidence_result: ConfidenceResult
    executed: bool
    execution_logs: List[str]

    async def save_learning(self):
        """Save successful execution to Long Term Memory (Pinecone)"""
        if self.executed and self.proposal.plan and self.proposal.plan.title:
            client = await get_pinecone_client()
            # We assume root cause is available from the proposal context, 
            # or we might need to pass the full AIRecommendation.
            # For now, using Title as Summary/Action.
            await client.store_incident(
                incident_id=f"learned_{self.proposal.plan.title.replace(' ', '_').lower()}",
                summary=f"{self.proposal.plan.title}: {self.proposal.plan.reasoning}",
                root_cause=self.proposal.plan.reasoning,
                recommended_action=self.proposal.plan.title
            )

class RemediationAgent:
    def __init__(self, feedback_store_path: str = "feedback.json"):
        self.feedback_store = FeedbackStore(feedback_store_path)
        self.confidence_engine = ConfidenceScorer(self.feedback_store)
        
    def run(self, proposal: RemediationProposal) -> AgentResult:
        """
        Run the Remediation Execution loop (The 'Act' Phase).
        
        Args:
            proposal: The fully formed proposal from the AI Adapter.
        """
        # 1. Evaluate (Safety & Confidence)
        result = self.confidence_engine.evaluate(proposal, proposal.confidence_score)
        print(f"[Agent] Confidence Evaluation: {result.decision} (Score: {result.final_score:.2f})")
        
        # 2. Act
        executed = False
        logs = []
        
        if result.decision == SafetyLevel.SAFE:
            print("[Agent] Auto-Execution Allowed. Running actions...")
            success = self._execute_actions(proposal.actions, logs)
            executed = True
            
            # Record feedback loop
            # Using plan title as signature
            self.feedback_store.record_feedback(proposal.plan.title, success)
            # Record feedback loop
            # Using plan title as signature
            self.feedback_store.record_feedback(proposal.plan.title, success)
            logs.append(f"Recorded feedback for '{proposal.plan.title}': Success={success}")
            
            # Note: We can't call async pinecone here directly if run() is synchronous.
            # The caller (orchestrator) should call result.save_learning()
            
            
        elif result.decision == SafetyLevel.REQUIRE_APPROVAL:
            print("[Agent] Approval Required. Returning proposal for HITL.")
            logs.append("Execution blocked: Human approval required.")
            
        elif result.decision == SafetyLevel.BLOCKED:
            print("[Agent] Action Blocked by Safety Policy.")
            logs.append("Execution blocked: Dangerous commands detected.")
            
        return AgentResult(
            proposal=proposal,
            confidence_result=result,
            executed=executed,
            execution_logs=logs
        )

    def _execute_actions(self, actions: List[RemediationAction], logs: List[str]) -> bool:
        """
        Execute the proposed actions.
        """
        all_success = True
        for action in actions:
            cmd_str = action.to_string()
            logs.append(f"Executing: {cmd_str}")
            
            # Double check safety just in case
            if SafetyPolicy.evaluate_command(cmd_str) == SafetyLevel.BLOCKED:
                logs.append(f"RUNTIME BLOCKED: {cmd_str}")
                all_success = False
                continue
                
            # Simulate execution for now (In real system: subprocess.run)
            print(f"  -> Ran '{cmd_str}'")
            
        return all_success

