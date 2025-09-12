#!/usr/bin/env python3
"""
Comprehensive test to mimic the web interface exclude flow
"""

import sys
import os

# Add the code directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from web.services import orchestrator as orch
from deck_builder.include_exclude_utils import parse_card_list_input

def test_web_exclude_flow():
    """Test the complete exclude flow as it would happen from the web interface"""
    
    print("=== Testing Complete Web Exclude Flow ===")
    
    # Simulate session data with exclude_cards
    exclude_input = """Sol Ring
Byrke, Long Ear of the Law
Burrowguard Mentor
Hare Apparent"""
    
    print(f"1. Parsing exclude input: {repr(exclude_input)}")
    exclude_list = parse_card_list_input(exclude_input.strip())
    print(f"   Parsed to: {exclude_list}")
    
    # Simulate session data
    mock_session = {
        "commander": "Alesha, Who Smiles at Death",
        "tags": ["Humans"],
        "bracket": 3,
        "tag_mode": "AND",
        "ideals": orch.ideal_defaults(),
        "use_owned_only": False,
        "prefer_owned": False,
        "locks": [],
        "custom_export_base": None,
        "multi_copy": None,
        "prefer_combos": False,
        "combo_target_count": 2,
        "combo_balance": "mix",
        "exclude_cards": exclude_list,  # This is the key
    }
    
    print(f"2. Session exclude_cards: {mock_session.get('exclude_cards')}")
    
    # Test start_build_ctx
    print("3. Creating build context...")
    try:
        ctx = orch.start_build_ctx(
            commander=mock_session.get("commander"),
            tags=mock_session.get("tags", []),
            bracket=mock_session.get("bracket", 3),
            ideals=mock_session.get("ideals", {}),
            tag_mode=mock_session.get("tag_mode", "AND"),
            use_owned_only=mock_session.get("use_owned_only", False),
            prefer_owned=mock_session.get("prefer_owned", False),
            owned_names=None,
            locks=mock_session.get("locks", []),
            custom_export_base=mock_session.get("custom_export_base"),
            multi_copy=mock_session.get("multi_copy"),
            prefer_combos=mock_session.get("prefer_combos", False),
            combo_target_count=mock_session.get("combo_target_count", 2),
            combo_balance=mock_session.get("combo_balance", "mix"),
            exclude_cards=mock_session.get("exclude_cards"),
        )
        print("   ✓ Build context created successfully")
        print(f"   Context exclude_cards: {ctx.get('exclude_cards')}")

        # Test running the first stage
        print("4. Running first build stage...")
        result = orch.run_stage(ctx, rerun=False, show_skipped=False)
        print(f"   ✓ Stage completed: {result.get('label', 'Unknown')}")
        print(f"   Stage done: {result.get('done', False)}")

        # Check if there were any exclude-related messages in output
        output = result.get('output', [])
        exclude_messages = [msg for msg in output if 'exclude' in msg.lower() or 'excluded' in msg.lower()]
        if exclude_messages:
            print("5. Exclude-related output found:")
            for msg in exclude_messages:
                print(f"   - {msg}")
        else:
            print("5. ⚠️  No exclude-related output found in stage result")
            print("   This might indicate the filtering isn't working")

    except Exception as e:
        print(f"❌ Error during build: {e}")
        import traceback
        traceback.print_exc()
        assert False

if __name__ == "__main__":
    success = test_web_exclude_flow()
    sys.exit(0 if success else 1)
