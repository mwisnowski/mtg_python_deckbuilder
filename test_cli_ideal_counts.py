#!/usr/bin/env python3
"""
Quick test script to verify CLI ideal count functionality works correctly.
"""

import subprocess
import json
import os

def test_cli_ideal_counts():
    """Test that CLI ideal count arguments work correctly."""
    print("Testing CLI ideal count arguments...")
    
    # Test dry-run with various ideal count CLI args
    cmd = [
        "python", "code/headless_runner.py",
        "--commander", "Aang, Airbending Master",
        "--creature-count", "30",
        "--land-count", "37", 
        "--ramp-count", "10",
        "--removal-count", "12",
        "--basic-land-count", "18",
        "--dry-run"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    
    if result.returncode != 0:
        print(f"❌ Command failed: {result.stderr}")
        return False
    
    try:
        config = json.loads(result.stdout)
        ideal_counts = config.get("ideal_counts", {})
        
        # Verify CLI args took effect
        expected = {
            "creatures": 30,
            "lands": 37,
            "ramp": 10, 
            "removal": 12,
            "basic_lands": 18
        }
        
        for key, expected_val in expected.items():
            actual_val = ideal_counts.get(key)
            if actual_val != expected_val:
                print(f"❌ {key}: expected {expected_val}, got {actual_val}")
                return False
            print(f"✅ {key}: {actual_val}")
        
        print("✅ All CLI ideal count arguments working correctly!")
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse JSON output: {e}")
        print(f"Output was: {result.stdout}")
        return False

def test_help_contains_types():
    """Test that help text shows value types."""
    print("\nTesting help text contains type information...")
    
    cmd = ["python", "code/headless_runner.py", "--help"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    
    if result.returncode != 0:
        print(f"❌ Help command failed: {result.stderr}")
        return False
    
    help_text = result.stdout
    
    # Check for type indicators
    type_indicators = [
        "PATH", "NAME", "INT", "BOOL", "CARDS", "MODE", "1-5"
    ]
    
    missing = []
    for indicator in type_indicators:
        if indicator not in help_text:
            missing.append(indicator)
    
    if missing:
        print(f"❌ Missing type indicators: {missing}")
        return False
    
    # Check for organized sections
    sections = [
        "Ideal Deck Composition:",
        "Land Configuration:", 
        "Card Type Toggles:",
        "Include/Exclude Cards:"
    ]
    
    missing_sections = []
    for section in sections:
        if section not in help_text:
            missing_sections.append(section)
    
    if missing_sections:
        print(f"❌ Missing help sections: {missing_sections}")
        return False
    
    print("✅ Help text contains proper type information and sections!")
    return True

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    success = True
    success &= test_cli_ideal_counts()
    success &= test_help_contains_types()
    
    if success:
        print("\n🎉 All tests passed! CLI ideal count functionality working correctly.")
    else:
        print("\n❌ Some tests failed.")
    
    exit(0 if success else 1)
