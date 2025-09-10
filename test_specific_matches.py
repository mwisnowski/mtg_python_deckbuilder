#!/usr/bin/env python3
"""Test improved matching for specific cases that were problematic"""

import requests

# Test the specific cases from the screenshots
test_cases = [
    ("lightn", "Should prioritize Lightning Bolt over Blightning/Flight"),
    ("cahso warp", "Should clearly find Chaos Warp first"),
    ("bolt", "Should find Lightning Bolt"),
    ("warp", "Should find Chaos Warp")
]

for input_text, description in test_cases:
    print(f"\n🔍 Testing: '{input_text}' ({description})")
    print("=" * 70)
    
    test_data = {
        "include_cards": input_text,
        "exclude_cards": "",
        "commander": "",
        "enforcement_mode": "warn",
        "allow_illegal": "false",
        "fuzzy_matching": "true"
    }
    
    try:
        response = requests.post(
            "http://localhost:8080/build/validate/include_exclude",
            data=test_data,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check results
            if data.get("confirmation_needed"):
                print("🔄 Confirmation modal would show:")
                for item in data["confirmation_needed"]:
                    print(f"   Input: '{item['input']}'")
                    print(f"   Confidence: {item['confidence']:.1%}")
                    print(f"   Top suggestions:")
                    for i, suggestion in enumerate(item['suggestions'][:5], 1):
                        print(f"     {i}. {suggestion}")
            elif data.get("includes", {}).get("legal"):
                fuzzy = data["includes"].get("fuzzy_matches", {})
                if input_text in fuzzy:
                    print(f"✅ Auto-accepted: '{input_text}' → '{fuzzy[input_text]}'")
                else:
                    print(f"✅ Exact match: {data['includes']['legal']}")
            else:
                print("❌ No matches found")
        else:
            print(f"❌ HTTP {response.status_code}")
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

print(f"\n💡 Testing complete! Check if Lightning/Chaos suggestions are now prioritized.")
