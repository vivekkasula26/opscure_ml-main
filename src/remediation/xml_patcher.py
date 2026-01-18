
import xml.etree.ElementTree as ET
import subprocess
import os
from typing import Optional, Tuple
from dataclasses import dataclass

@dataclass
class XmlPatchResult:
    success: bool
    message: str
    diff: Optional[str] = None

class XmlPatcher:
    """
    Robust XML/POM Patcher.
    
    Handles structural edits (e.g., removing blocks) rather than line-based edits
    to ensure validity.
    """
    
    @staticmethod
    def remove_dependency(file_path: str, artifact_id: str) -> XmlPatchResult:
        """
        Removes a <dependency> block with the matching artifactId.
        """
        return XmlPatcher._remove_block_by_child_tag(file_path, "dependency", "artifactId", artifact_id)
        
    @staticmethod
    def remove_plugin(file_path: str, artifact_id: str) -> XmlPatchResult:
        """
        Removes a <plugin> block with the matching artifactId.
        """
        return XmlPatcher._remove_block_by_child_tag(file_path, "plugin", "artifactId", artifact_id)

    @staticmethod
    def _remove_block_by_child_tag(file_path: str, parent_tag: str, child_tag: str, child_value: str) -> XmlPatchResult:
        try:
            # 1. Parse
            # Note: ET drops comments/formatting by default. 
            # For a real robust tool, we might want 'lxml', but we stick to stdlib for now as per plan.
            # We must warn that re-serialization might change formatting.
            
            # Helper to register namespace
            try:
                events = ET.iterparse(file_path, events=('start-ns',))
                for event, (prefix, uri) in events:
                    if not prefix: # Default namespace
                         ET.register_namespace('', uri)
            except Exception:
                pass

            tree = ET.parse(file_path)
            root = tree.getroot()
            
            # 2. Namespace handling
            # Maven POMs usually have a namespace. ElementTree requires explicit namespace map.
            # Simplified: strip namespaces for searching or handle wildcard?
            # Let's try to handle the default namespace generic logic if possible, 
            # or just recursive search.
            
            # Simple recursive find for the node
            # We want to find a 'parent_tag' (e.g. dependency) that has a 'child_tag' (artifactId) == text
            
            # We need to find the *parent* of the node to remove it.
            # Map parent to children
            parent_map = {c: p for p in root.iter() for c in p}
            
            found_node = None
            found_parent = None
            
            # Iterate all elements that match the tag name (ignoring namespace for simplicity in search)
            for elem in root.iter():
                # Check if tag ends with the target tag (handling {xmlns}tag)
                if elem.tag.endswith(parent_tag) or elem.tag == parent_tag:
                    # Check children
                    for child in elem:
                        if (child.tag.endswith(child_tag) or child.tag == child_tag) and child.text == child_value:
                            found_node = elem
                            break
                if found_node:
                    break
            
            if not found_node:
                return XmlPatchResult(False, f"Could not find <{parent_tag}> with {child_tag}={child_value}")
                
            # 3. Remove
            # Need the parent of found_node
            found_parent = parent_map.get(found_node)
            if not found_parent and found_node != root:
                 # Should not happen unless root is the match?
                 return XmlPatchResult(False, "Could not find parent node provided match.")
                 
            if found_parent:
                found_parent.remove(found_node)
            else:
                # Removing root?
                pass
                
            # 4. Save
            tree.write(file_path, encoding="utf-8", xml_declaration=True)
            
            return XmlPatchResult(True, f"Successfully removed <{parent_tag}> for {child_value}")
            
        except ET.ParseError as e:
            return XmlPatchResult(False, f"XML Parse Error: {e}")
        except Exception as e:
            return XmlPatchResult(False, f"Error patching XML: {e}")

    @staticmethod
    def validate_xml(file_path: str) -> Tuple[bool, str]:
        """
        Validates the XML file using xmllint.
        """
        # Check if xmllint exists
        if os.system("which xmllint > /dev/null 2>&1") != 0:
            # Fallback to python parse check
            try:
                ET.parse(file_path)
                return True, "Valid XML (checked via ElementTree)"
            except ET.ParseError as e:
                return False, str(e)

        # Run xmllint
        try:
            result = subprocess.run(
                ["xmllint", "--noout", file_path],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return True, "Valid XML"
            else:
                return False, result.stderr.strip()
        except Exception as e:
            return False, str(e)
