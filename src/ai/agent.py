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
from src.common.types import CorrelationBundle, GitConfig
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
            success = self._execute_actions(proposal.actions, logs, proposal.git_config)
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

    def _execute_actions(self, actions: List[RemediationAction], logs: List[str], git_config: Optional[GitConfig] = None) -> bool:
        """
        Execute the proposed actions.
        """
        from src.remediation.patcher import CodePatcher 

        all_success = True
        for action in actions:
            # Handle FILE_EDIT
            if action.type == ActionType.FILE_EDIT:
                logs.append(f"Attempting Smart Patch on {action.file_path}...")
                
                # Check for critical missing info
                if not action.file_path or not action.original_context or not action.replacement_text:
                    logs.append(f"FAILED: Malformed FILE_EDIT action. Missing path/context/replacement.")
                    all_success = False
                    continue
                    
                patch_result = CodePatcher.apply_patch(
                    action.file_path,
                    action.original_context,
                    action.replacement_text
                )
                
                if patch_result.success:
                    logs.append(f"SUCCESS: Patch applied to {action.file_path}")
                    print(f"  -> Applied Smart Patch to {action.file_path}")
                    # Optionally log the diff
                    # logs.append(f"Diff:\n{patch_result.diff}")
                else:
                    logs.append(f"FAILED: {patch_result.message}")
                    print(f"  -> Patch Failed: {patch_result.message}")
                    all_success = False
                continue

            # Handle XML_EDIT
            if action.type == ActionType.XML_EDIT:
                from src.remediation.xml_patcher import XmlPatcher
                logs.append(f"Attempting Structured XML Edit on {action.file_path}...")
                
                if not action.file_path or not action.xml_selector or not action.xml_value:
                    logs.append("FAILED: Malformed XML_EDIT. Missing path/selector/value.")
                    all_success = False
                    continue

                # Execute Patch
                if action.xml_selector == "dependency":
                    res = XmlPatcher.remove_dependency(action.file_path, action.xml_value)
                elif action.xml_selector == "plugin":
                    res = XmlPatcher.remove_plugin(action.file_path, action.xml_value)
                else:
                    res = XmlPatcher.remove_dependency(action.file_path, action.xml_value) # Default? Or Error
                    logs.append(f"FAILED: Unknown selector {action.xml_selector}")
                    all_success = False
                    continue
                    
                if not res.success:
                    logs.append(f"FAILED: {res.message}")
                    print(f"  -> XML Patch Failed: {res.message}")
                    all_success = False
                    continue
                    
                logs.append(f"SUCCESS: XML Patch applied. {res.message}")
                print(f"  -> Applied XML Patch to {action.file_path}")
                
                # Validation Step (The "Safety Check")
                # 1. Structural Check
                valid, msg = XmlPatcher.validate_xml(action.file_path)
                if not valid:
                    logs.append(f"VALIDATION FAILED: XML structure invalid. {msg}")
                    print(f"  -> Validation Failed: {msg}")
                    all_success = False
                    continue
                    
                # 2. Logic Check (mvn validate)
                if action.file_path.endswith("pom.xml"):
                    logs.append("Running 'mvn validate'...")
                    print("  -> Verifying with 'mvn validate'...")
                    try:
                         import subprocess
                         cwd = os.path.dirname(action.file_path)
                         # Use -q to be quiet, -DskipTests to be fast
                         proc = subprocess.run(
                             ["mvn", "validate", "-q", "-DskipTests"], 
                             cwd=cwd if cwd else ".", 
                             capture_output=True, 
                             text=True
                         )
                         if proc.returncode != 0:
                             logs.append(f"VALIDATION FAILED: mvn validate returned {proc.returncode}")
                             print(f"  -> 'mvn validate' Failed: {proc.stderr[:100]}...")
                             all_success = False
                         else:
                             logs.append("VALIDATION SUCCESS: Project validates.")
                             print("  -> 'mvn validate' Passed.")
                    except Exception as e:
                        logs.append(f"VALIDATION ERROR: Could not run mvn. {e}")
                
                continue

            # Handle RUNTIME_OP
            if action.type == ActionType.RUNTIME_OP:
                cmd_str = action.command
                logs.append(f"Executing Runtime Operation: {cmd_str}")
                print(f"  -> Executing Runtime Op: '{cmd_str}'")
                # In real implementation:
                # if "kubectl" in cmd_str: run_kubectl(cmd_str)
                # elif "restart" in cmd_str: ...
                # For now, we simulate success
                continue

            # Handle COMMAND
            cmd_str = action.to_string()
            
            # Apply Git Config if available
            if git_config and cmd_str.strip().startswith("git "):
                # Inject config flags
                # e.g., "git commit ..." -> "git -c user.name='...' -c user.email='...' commit ..."
                parts = cmd_str.strip().split(" ", 1)
                base = parts[0]
                rest = parts[1] if len(parts) > 1 else ""
                
                config_flags = f"-c user.name='{git_config.user_name}' -c user.email='{git_config.user_email}'"
                cmd_str = f"{base} {config_flags} {rest}"
                
            logs.append(f"Executing: {cmd_str}")
            
            # Double check safety just in case
            if SafetyPolicy.evaluate_command(cmd_str) == SafetyLevel.BLOCKED:
                logs.append(f"RUNTIME BLOCKED: {cmd_str}")
                all_success = False
                continue
                
            # Simulate execution for now (In real system: subprocess.run)
            print(f"  -> Ran '{cmd_str}'")
            
        return all_success

