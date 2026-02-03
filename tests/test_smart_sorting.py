
import unittest
from src.ai.prompt_builder import PromptBuilder
from src.ai.summarizer import Summarizer
from src.common.types import CorrelationBundle, LogPattern

class TestSmartSorting(unittest.TestCase):
    def test_smart_sorting_prioritization(self):
        print("\n=== Testing Smart Sorting Logic ===")
        
        # Create 50 log patterns
        patterns = []
        
        # 49 "Info" patterns with high count (Noise)
        for i in range(49):
            patterns.append(LogPattern(
                pattern=f"Info: Application loop iteration {i}",
                count=100,
                firstOccurrence="2025-01-01T12:00:00Z",
                lastOccurrence="2025-01-01T12:05:00Z"
            ))
            
        # 1 "Fatal" pattern with low count (Signal)
        fatal_pattern = LogPattern(
            pattern="FATAL: Database Connection Refused",
            count=1,
            firstOccurrence="2025-01-01T12:01:00Z",
            lastOccurrence="2025-01-01T12:01:00Z",
            errorClass="ConnectionRefusedError" 
        )
        patterns.append(fatal_pattern)
        
        # Verify Input State
        print(f"Input: {len(patterns)} patterns.")
        print(f" - Noise: 49 (Count=100)")
        print(f" - Signal: 1 (Count=1, FATAL)")
        
        # Create Bundle
        bundle = CorrelationBundle(
            windowStart="now", 
            windowEnd="now", 
            logPatterns=patterns
        )
        
        # Test 1: Prompt Builder (Top 20)
        print("\n[Test 1] PromptBuilder._get_prioritized_patterns")
        sorted_patterns = PromptBuilder._get_prioritized_patterns(bundle.logPatterns, limit=20)
        
        print(f"Result: Selected {len(sorted_patterns)} patterns.")
        first = sorted_patterns[0]
        print(f"Top Pattern: {first.pattern}")
        
        # Assertions
        self.assertEqual(len(sorted_patterns), 20)
        self.assertIn("FATAL", first.pattern, "Fatal error should be the #1 pattern despite low count")
        
        # Test 2: Summarizer (Top 3)
        print("\n[Test 2] Summarizer.summarize_bundle")
        summary = Summarizer.summarize_bundle(bundle)
        print(f"Summary Output: {summary}")
        
        # Assertions
        self.assertIn("FATAL", summary, "Summary should include the FATAL error")
        self.assertIn("Database Connection Refused", summary)
        
        print("\nSUCCESS: Smart sorting correctly prioritized the hidden fatal error.")

if __name__ == "__main__":
    unittest.main()
