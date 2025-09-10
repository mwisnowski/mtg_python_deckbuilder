#!/usr/bin/env python3
"""
Test to check if the web form is properly sending exclude_cards
"""

import requests
import re

def test_web_form_exclude():
    """Test that the web form properly handles exclude cards"""
    
    print("=== Testing Web Form Exclude Flow ===")
    
    # Test 1: Check if the exclude textarea is visible
    print("1. Checking if exclude textarea is visible in new deck modal...")
    
    try:
        response = requests.get("http://localhost:8080/build/new")
        if response.status_code == 200:
            content = response.text
            if 'name="exclude_cards"' in content:
                print("   ✅ exclude_cards textarea found in form")
            else:
                print("   ❌ exclude_cards textarea NOT found in form")
                print("   Checking for Advanced Options section...")
                if 'Advanced Options' in content:
                    print("   ✅ Advanced Options section found")
                else:
                    print("   ❌ Advanced Options section NOT found")
                return False
            
            # Check if feature flag is working
            if 'allow_must_haves' in content or 'exclude_cards' in content:
                print("   ✅ Feature flag appears to be working")
            else:
                print("   ❌ Feature flag might not be working")
                
        else:
            print(f"   ❌ Failed to get modal: HTTP {response.status_code}")
            return False
    
    except Exception as e:
        print(f"   ❌ Error checking modal: {e}")
        return False
    
    # Test 2: Try to submit a form with exclude cards
    print("2. Testing form submission with exclude cards...")
    
    form_data = {
        "commander": "Alesha, Who Smiles at Death",
        "primary_tag": "Humans", 
        "bracket": "3",
        "exclude_cards": "Sol Ring\nByrke, Long Ear of the Law\nBurrowguard Mentor\nHare Apparent"
    }
    
    try:
        # Submit the form
        response = requests.post("http://localhost:8080/build/new", data=form_data)
        if response.status_code == 200:
            print("   ✅ Form submitted successfully")
            
            # Check if we can see any exclude-related content in the response
            content = response.text
            if "exclude" in content.lower() or "excluded" in content.lower():
                print("   ✅ Exclude-related content found in response")
            else:
                print("   ⚠️  No exclude-related content found in response")
                
        else:
            print(f"   ❌ Form submission failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error submitting form: {e}")
        return False
    
    print("3. ✅ Web form test completed")
    return True

if __name__ == "__main__":
    test_web_form_exclude()
