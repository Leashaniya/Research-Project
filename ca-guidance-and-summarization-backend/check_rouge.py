#!/usr/bin/env python3
"""Diagnostic script to check rouge-score installation."""

import sys
import os

print("=" * 60)
print("ROUGE-SCORE DIAGNOSTIC CHECK")
print("=" * 60)
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path[:3]}...")  # Show first 3 paths
print()

# Check if we're in a virtual environment
venv = os.environ.get('VIRTUAL_ENV')
if venv:
    print(f"✓ Virtual environment detected: {venv}")
else:
    print("⚠ No virtual environment detected")
print()

# Try to import rouge_score
print("Attempting to import rouge_score...")
try:
    from rouge_score import rouge_scorer
    print("✓ SUCCESS: rouge_score imported successfully!")
    print(f"  Location: {rouge_scorer.__file__}")
    
    # Test basic functionality
    scorer = rouge_scorer.RougeScorer(['rouge1'], use_stemmer=True)
    scores = scorer.score("The quick brown fox", "The quick brown dog")
    print("✓ SUCCESS: ROUGE scorer works correctly!")
    print(f"  Test ROUGE-1 F-measure: {scores['rouge1'].fmeasure:.4f}")
    
except ImportError as e:
    print("✗ FAILED: Cannot import rouge_score")
    print(f"  Error: {e}")
    print()
    print("SOLUTION:")
    print("1. Activate your virtual environment:")
    print("   PowerShell: .venv\\Scripts\\Activate.ps1")
    print("   CMD: .venv\\Scripts\\activate.bat")
    print("   Bash: source .venv/bin/activate")
    print()
    print("2. Then install rouge-score:")
    print("   pip install rouge-score")
    print()
    print("3. Or install in the current Python:")
    print(f"   {sys.executable} -m pip install rouge-score")
    
except Exception as e:
    print(f"✗ FAILED: Error using rouge_score: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 60)

