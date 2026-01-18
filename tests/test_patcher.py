import unittest
import os
from src.remediation.patcher import CodePatcher, PatchResult

class TestCodePatcher(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_target.txt"
        with open(self.test_file, "w") as f:
            f.write("Line 1\nLine 2\nLine 3\nLine 4\n")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_exact_match_success(self):
        original = "Line 2\nLine 3\n"
        replacement = "Line 2 Modified\nLine 3 Modified\n"
        
        result = CodePatcher.apply_patch(self.test_file, original, replacement)
        
        self.assertTrue(result.success)
        with open(self.test_file, "r") as f:
            content = f.read()
        self.assertIn("Line 2 Modified", content)
        self.assertNotIn("Line 2\n", content)

    def test_drift_fail(self):
        # Simulate drift by modifying the file first
        with open(self.test_file, "w") as f:
            f.write("Line 1\nLine 2 Changed\nLine 3\nLine 4\n")
            
        original = "Line 2\nLine 3\n" # Expects original
        replacement = "Fix\n"
        
        result = CodePatcher.apply_patch(self.test_file, original, replacement)
        
        self.assertFalse(result.success)
        self.assertIn("Context not found", result.message)

    def test_ambiguous_context_fail(self):
        with open(self.test_file, "w") as f:
            f.write("repeat\nrepeat\nrepeat\n")
            
        original = "repeat\n"
        replacement = "fixed\n"
        
        result = CodePatcher.apply_patch(self.test_file, original, replacement)
        
        self.assertFalse(result.success)
        self.assertIn("Ambiguous", result.message)

if __name__ == "__main__":
    unittest.main()
