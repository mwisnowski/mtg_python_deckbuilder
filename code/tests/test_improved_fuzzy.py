#!/usr/bin/env python3
"""Test improved fuzzy matching algorithm with the new endpoint"""

import requests
import json

def test_improved_fuzzy():
    """Test improved fuzzy matching with various inputs"""
    
    test_cases = [
        ("lightn", "Should find Lightning cards"),
        ("light", "Should find Light cards"),
        ("bolt", "Should find Bolt cards"), 
        ("blightni", "Should find Blightning"),
        ("lightn bo", "Should be unclear match")
    ]
    
    for input_text, description in test_cases:
        print(f"\n🔍 Testing: '{input_text}' ({description})")
        print("=" * 60)
        
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
                    print(f"🔄 Fuzzy confirmation needed for '{input_text}'")
                    for item in data["confirmation_needed"]:
                        print(f"   Best: '{item['best_match']}' ({item['confidence']:.1%})")
                        if item.get('suggestions'):
                            print(f"   Top 3:")
                            for i, suggestion in enumerate(item['suggestions'][:3], 1):
                                print(f"     {i}. {suggestion}")
                elif data.get("valid"):
                    print(f"✅ Auto-accepted: {[card['name'] for card in data['valid']]}")
                    # Show best match info if available
                    for card in data['valid']:
                        if card.get('fuzzy_match_info'):
                            print(f"   Fuzzy matched '{input_text}' → '{card['name']}' ({card['fuzzy_match_info'].get('confidence', 0):.1%})")
                elif data.get("invalid"):
                    print(f"❌ Invalid: {[card['input'] for card in data['invalid']]}")
                else:
                    print(f"❓ No clear result for '{input_text}'")
                    print(f"Response keys: {list(data.keys())}")
            else:
                print(f"❌ HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    print("🧪 Testing Improved Fuzzy Match Algorithm")
    print("==========================================")
    test_improved_fuzzy()
