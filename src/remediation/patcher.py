"""
Code Patcher Module

Handles robust, validation-based code modification.
Prevents "blind" edits by requiring context matching.
"""

import os
import difflib
from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class PatchResult:
    success: bool
    message: str
    diff: str = ""

class CodePatcher:
    """
    Applies patches to files with context verification.
    """
    
    @staticmethod
    def apply_patch(file_path: str, original_context: str, replacement_text: str) -> PatchResult:
        """
        Applies a replacement to a file ONLY if the original_context matches exactly.
        
        Args:
            file_path: Absolute path to the file.
            original_context: The exact lines of code to replace (including newlines/indentation).
            replacement_text: The new lines of code.
            
        Returns:
            PatchResult: Success/Failure status and details.
        """
        if not os.path.exists(file_path):
            return PatchResult(False, f"File not found: {file_path}")
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return PatchResult(False, f"Failed to read file: {str(e)}")

        # Normalize line endings to avoid \r\n vs \n issues
        # We'll split by lines to handle specific line matching if needed, 
        # but simple string replacement is robust IF context is sufficient.
        
        # However, to be "Smart", we should be careful about whitespace.
        # For this MVP, exact string match is the safest "Drift Check".
        # If it doesn't match exactly, something changed.
        
        # Strip trailing newlines from context for matching flexibility if the user copy-pasted badly?
        # No, strict is better for safety.
        
        if original_context not in content:
            # Try to help debugging: check if it's there but with different whitespace
            normalized_context = " ".join(original_context.split())
            normalized_content = " ".join(content.split())
            
            if normalized_context in normalized_content:
                return PatchResult(False, "Context mismatch (Whitespace difference). Ensure exact indentation.")
            
            return PatchResult(False, "Context not found. The code may have changed (Drift Detected).")
            
        # Check for ambiguity
        if content.count(original_context) > 1:
            return PatchResult(False, "Ambiguous context: Found multiple matches. Provide more context.")
            
        # Apply replacement
        new_content = content.replace(original_context, replacement_text)
        
        # Create diff for audit
        diff = difflib.unified_diff(
            content.splitlines(),
            new_content.splitlines(),
            fromfile=file_path,
            tofile=file_path,
            lineterm=""
        )
        diff_text = "\n".join(diff)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return PatchResult(False, f"Failed to write file: {str(e)}")
            
        return PatchResult(True, "Patch applied successfully", diff=diff_text)
