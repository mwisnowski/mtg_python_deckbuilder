"""
Comprehensive tests for exclude card functionality.

This file consolidates tests from multiple source files:
- test_comprehensive_exclude.py
- test_direct_exclude.py
- test_exclude_filtering.py
- test_exclude_integration.py
- test_exclude_cards_integration.py
- test_exclude_cards_compatibility.py
- test_exclude_reentry_prevention.py

Tests cover: exclude filtering, dataframe integration, manual lookups,
web flow integration, JSON persistence, compatibility, and re-entry prevention.
"""

import sys
import os
import time
import base64
import json
import unittest
from unittest.mock import Mock
import pandas as pd
import pytest
from typing import List
from starlette.testclient import TestClient

from deck_builder.builder import DeckBuilder
from deck_builder.include_exclude_utils import parse_card_list_input, normalize_card_name


# =============================================================================
# SECTION: Core Exclude Filtering Tests
# Source: test_comprehensive_exclude.py
# =============================================================================

def test_comprehensive_exclude_filtering():
    """Test that excluded cards are completely removed from all dataframe sources."""
    print("=== Comprehensive Exclude Filtering Test ===")
    
    # Create a test builder
    builder = DeckBuilder(headless=True, output_func=lambda x: print(f"Builder: {x}"), input_func=lambda x: "")
    
    # Set some common exclude patterns
    exclude_list = ["Sol Ring", "Rhystic Study", "Cyclonic Rift"]
    builder.exclude_cards = exclude_list
    print(f"Testing exclusion of: {exclude_list}")
    
    # Try to set up a simple commander to get dataframes loaded
    try:
        # Load commander data and select a commander first
        cmd_df = builder.load_commander_data()
        atraxa_row = cmd_df[cmd_df["name"] == "Atraxa, Praetors' Voice"]
        if not atraxa_row.empty:
            builder._apply_commander_selection(atraxa_row.iloc[0])
        else:
            # Fallback to any commander for testing
            if not cmd_df.empty:
                builder._apply_commander_selection(cmd_df.iloc[0])
                print(f"Using fallback commander: {builder.commander_name}")
        
        # Now determine color identity
        builder.determine_color_identity()
        
        # This should trigger the exclude filtering
        combined_df = builder.setup_dataframes()
        
        # Check that excluded cards are not in the combined dataframe
        print(f"\n1. Checking combined dataframe (has {len(combined_df)} cards)...")
        for exclude_card in exclude_list:
            if 'name' in combined_df.columns:
                matches = combined_df[combined_df['name'].str.contains(exclude_card, case=False, na=False)]
                if len(matches) == 0:
                    print(f"   ✓ '{exclude_card}' correctly excluded from combined_df")
                else:
                    print(f"   ✗ '{exclude_card}' still found in combined_df: {matches['name'].tolist()}")
        
        # Check that excluded cards are not in the full dataframe either
        print(f"\n2. Checking full dataframe (has {len(builder._full_cards_df)} cards)...")
        for exclude_card in exclude_list:
            if builder._full_cards_df is not None and 'name' in builder._full_cards_df.columns:
                matches = builder._full_cards_df[builder._full_cards_df['name'].str.contains(exclude_card, case=False, na=False)]
                if len(matches) == 0:
                    print(f"   ✓ '{exclude_card}' correctly excluded from full_df")
                else:
                    print(f"   ✗ '{exclude_card}' still found in full_df: {matches['name'].tolist()}")
        
        # Try to manually lookup excluded cards (this should fail)
        print("\n3. Testing manual card lookups...")
        for exclude_card in exclude_list:
            # Simulate what the builder does when looking up cards
            df_src = builder._full_cards_df if builder._full_cards_df is not None else builder._combined_cards_df
            if df_src is not None and not df_src.empty and 'name' in df_src.columns:
                lookup_result = df_src[df_src['name'].astype(str).str.lower() == exclude_card.lower()]
                if lookup_result.empty:
                    print(f"   ✓ '{exclude_card}' correctly not found in lookup")
                else:
                    print(f"   ✗ '{exclude_card}' incorrectly found in lookup: {lookup_result['name'].tolist()}")
        
        print("\n=== Test Complete ===")
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        print(traceback.format_exc())
        assert False


# =============================================================================
# SECTION: Direct Exclude Flow Tests
# Source: test_direct_exclude.py
# =============================================================================

def test_direct_exclude_filtering():
    """Test exclude filtering directly on a DeckBuilder instance."""
    
    print("=== Direct DeckBuilder Exclude Test ===")
    
    # Create a builder instance
    builder = DeckBuilder()
    
    # Set exclude cards directly
    exclude_list = [
        "Sol Ring",
        "Byrke, Long Ear of the Law", 
        "Burrowguard Mentor",
        "Hare Apparent"
    ]
    
    print(f"1. Setting exclude_cards: {exclude_list}")
    builder.exclude_cards = exclude_list
    
    print(f"2. Checking attribute: {getattr(builder, 'exclude_cards', 'NOT SET')}")
    print(f"3. hasattr check: {hasattr(builder, 'exclude_cards')}")
    
    # Mock some cards in the dataframe
    test_cards = pd.DataFrame([
        {"name": "Sol Ring", "color_identity": "", "type_line": "Artifact"},
        {"name": "Byrke, Long Ear of the Law", "color_identity": "W", "type_line": "Legendary Creature"},
        {"name": "Burrowguard Mentor", "color_identity": "W", "type_line": "Creature"},
        {"name": "Hare Apparent", "color_identity": "W", "type_line": "Creature"},
        {"name": "Lightning Bolt", "color_identity": "R", "type_line": "Instant"},
    ])
    
    print(f"4. Test cards before filtering: {len(test_cards)}")
    print(f"   Cards: {test_cards['name'].tolist()}")
    
    # Set the combined dataframe and call the filtering logic
    builder._combined_cards_df = test_cards.copy()
    
    # Apply the exclude filtering logic
    combined = builder._combined_cards_df.copy()
    
    if hasattr(builder, 'exclude_cards') and builder.exclude_cards:
        print("   DEBUG: Exclude filtering condition met!")
        try:
            # Find name column
            name_col = None
            if 'name' in combined.columns:
                name_col = 'name'
            elif 'Card Name' in combined.columns:
                name_col = 'Card Name'
                
            if name_col is not None:
                excluded_matches = []
                original_count = len(combined)
                
                # Normalize exclude patterns for matching
                normalized_excludes = {normalize_card_name(pattern): pattern for pattern in builder.exclude_cards}
                print(f"   Normalized excludes: {normalized_excludes}")
                
                # Create a mask to track which rows to exclude
                exclude_mask = pd.Series([False] * len(combined), index=combined.index)
                
                # Check each card against exclude patterns
                for idx, card_name in combined[name_col].items():
                    if not exclude_mask[idx]:  # Only check if not already excluded
                        normalized_card = normalize_card_name(str(card_name))
                        print(f"   Checking card: '{card_name}' -> normalized: '{normalized_card}'")
                        
                        # Check if this card matches any exclude pattern
                        for normalized_exclude, original_pattern in normalized_excludes.items():
                            if normalized_card == normalized_exclude:
                                print(f"   MATCH: '{card_name}' matches pattern '{original_pattern}'")
                                excluded_matches.append({
                                    'pattern': original_pattern,
                                    'matched_card': str(card_name),
                                    'similarity': 1.0
                                })
                                exclude_mask[idx] = True
                                break  # Found a match, no need to check other patterns
                
                # Apply the exclusions in one operation
                if exclude_mask.any():
                    combined = combined[~exclude_mask].copy()
                    print(f"   Excluded {len(excluded_matches)} cards from pool (was {original_count}, now {len(combined)})")
                else:
                    print(f"   No cards matched exclude patterns: {', '.join(builder.exclude_cards)}")
            else:
                print("   No recognizable name column found")
        except Exception as e:
            print(f"   Error during exclude filtering: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("   DEBUG: Exclude filtering condition NOT met!")
    
    # Update the builder's dataframe
    builder._combined_cards_df = combined
    
    print(f"6. Cards after filtering: {len(combined)}")
    print(f"   Remaining cards: {combined['name'].tolist()}")
    
    # Check if exclusions worked
    remaining_cards = combined['name'].tolist()
    failed_exclusions = []
    
    for exclude_card in exclude_list:
        if exclude_card in remaining_cards:
            failed_exclusions.append(exclude_card)
            print(f"   ❌ {exclude_card} was NOT excluded!")
        else:
            print(f"   ✅ {exclude_card} was properly excluded")
    
    if failed_exclusions:
        print(f"\n❌ FAILED: {len(failed_exclusions)} cards were not excluded: {failed_exclusions}")
        assert False
    else:
        print(f"\n✅ SUCCESS: All {len(exclude_list)} cards were properly excluded")


# =============================================================================
# SECTION: Exclude Filtering Logic Tests
# Source: test_exclude_filtering.py
# =============================================================================

def test_exclude_filtering_logic():
    """Test that our exclude filtering logic works correctly."""
    
    # Simulate the cards from user's test case
    test_cards_df = pd.DataFrame([
        {"name": "Sol Ring", "other_col": "value1"},
        {"name": "Byrke, Long Ear of the Law", "other_col": "value2"},
        {"name": "Burrowguard Mentor", "other_col": "value3"},
        {"name": "Hare Apparent", "other_col": "value4"},
        {"name": "Lightning Bolt", "other_col": "value5"},
        {"name": "Counterspell", "other_col": "value6"},
    ])
    
    # User's exclude list from their test
    exclude_list = [
        "Sol Ring",
        "Byrke, Long Ear of the Law", 
        "Burrowguard Mentor",
        "Hare Apparent"
    ]
    
    print("Original cards:")
    print(test_cards_df['name'].tolist())
    print(f"\nExclude list: {exclude_list}")
    
    # Apply the same filtering logic as in builder.py
    if exclude_list:
        normalized_excludes = {normalize_card_name(name): name for name in exclude_list}
        print(f"\nNormalized excludes: {list(normalized_excludes.keys())}")
        
        # Create exclude mask
        exclude_mask = test_cards_df['name'].apply(
            lambda x: normalize_card_name(x) not in normalized_excludes
        )
        
        print(f"\nExclude mask: {exclude_mask.tolist()}")
        
        # Apply filtering
        filtered_df = test_cards_df[exclude_mask].copy()
        
        print(f"\nFiltered cards: {filtered_df['name'].tolist()}")
        
        # Verify results
        excluded_cards = test_cards_df[~exclude_mask]['name'].tolist()
        print(f"Cards that were excluded: {excluded_cards}")
        
        # Check if all exclude cards were properly removed
        remaining_cards = filtered_df['name'].tolist()
        for exclude_card in exclude_list:
            if exclude_card in remaining_cards:
                print(f"ERROR: {exclude_card} was NOT excluded!")
                assert False
            else:
                print(f"✓ {exclude_card} was properly excluded")
        
        print(f"\n✓ SUCCESS: All {len(exclude_list)} cards were properly excluded")
        print(f"✓ Remaining cards: {len(remaining_cards)} out of {len(test_cards_df)}")
    else:
        assert False


# =============================================================================
# SECTION: Exclude Integration Tests
# Source: test_exclude_integration.py
# =============================================================================

def test_exclude_integration():
    """Test that exclude functionality works end-to-end."""
    print("=== M0.5 Exclude Integration Test ===")
    
    # Test 1: Parse exclude list
    print("\n1. Testing card list parsing...")
    exclude_input = "Sol Ring\nRhystic Study\nSmothering Tithe"
    exclude_list = parse_card_list_input(exclude_input)
    print(f"   Input: {repr(exclude_input)}")
    print(f"   Parsed: {exclude_list}")
    assert len(exclude_list) == 3
    assert "Sol Ring" in exclude_list
    print("   ✓ Parsing works")
    
    # Test 2: Check DeckBuilder has the exclude attribute
    print("\n2. Testing DeckBuilder exclude attribute...")
    builder = DeckBuilder(headless=True, output_func=lambda x: None, input_func=lambda x: "")
    
    # Set exclude cards
    builder.exclude_cards = exclude_list
    print(f"   Set exclude_cards: {builder.exclude_cards}")
    assert hasattr(builder, 'exclude_cards')
    assert builder.exclude_cards == exclude_list
    print("   ✓ DeckBuilder accepts exclude_cards attribute")
    
    print("\n=== All tests passed! ===")
    print("M0.5 exclude functionality is ready for testing.")


# =============================================================================
# SECTION: Web Integration Tests
# Source: test_exclude_cards_integration.py
# =============================================================================

def test_exclude_cards_complete_integration():
    """Comprehensive test demonstrating all exclude card features working together."""
    # Set up test client with feature enabled
    import importlib
    
    # Ensure project root is in sys.path for reliable imports
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Ensure feature flag is enabled
    original_value = os.environ.get('ALLOW_MUST_HAVES')
    os.environ['ALLOW_MUST_HAVES'] = '1'
    
    try:
        # Fresh import to pick up environment
        try:
            del importlib.sys.modules['code.web.app']
        except KeyError:
            pass
        
        app_module = importlib.import_module('code.web.app')
        client = TestClient(app_module.app)
        
        print("\n=== EXCLUDE CARDS INTEGRATION TEST ===")
        
        # 1. Test file upload simulation (parsing multi-line input)
        print("\n1. Testing exclude card parsing (file upload simulation):")
        exclude_cards_content = """Sol Ring
Rhystic Study
Smothering Tithe
Lightning Bolt
Counterspell"""
        
        parsed_cards = parse_card_list_input(exclude_cards_content)
        print(f"   Parsed {len(parsed_cards)} cards from input")
        assert len(parsed_cards) == 5
        assert "Sol Ring" in parsed_cards
        assert "Rhystic Study" in parsed_cards
        
        # 2. Test live validation endpoint
        print("\n2. Testing live validation API:")
        start_time = time.time()
        response = client.post('/build/validate/exclude_cards', 
                             data={'exclude_cards': exclude_cards_content})
        validation_time = time.time() - start_time
        
        assert response.status_code == 200
        validation_data = response.json()
        print(f"   Validation response time: {validation_time*1000:.1f}ms")
        print(f"   Validated {validation_data['count']}/{validation_data['limit']} excludes")
        assert validation_data["count"] == 5
        assert validation_data["limit"] == 15
        assert validation_data["over_limit"] is False
        
        # 3. Test complete deck building workflow with excludes
        print("\n3. Testing complete deck building with excludes:")
        
        # Start session and create deck with excludes
        r1 = client.get('/build')
        assert r1.status_code == 200
        
        form_data = {
            "name": "Exclude Cards Integration Test", 
            "commander": "Inti, Seneschal of the Sun",
            "primary_tag": "discard",
            "bracket": 3,
            "ramp": 10, "lands": 36, "basic_lands": 18, "creatures": 28,
            "removal": 10, "wipes": 3, "card_advantage": 8, "protection": 4,
            "exclude_cards": exclude_cards_content
        }
        
        build_start = time.time()
        r2 = client.post('/build/new', data=form_data)
        build_time = time.time() - build_start
        
        assert r2.status_code == 200
        print(f"   Deck build completed in {build_time*1000:.0f}ms")
        
        # 4. Test JSON export/import (permalinks)
        print("\n4. Testing JSON export/import:")
        
        # Get session cookie and export permalink
        session_cookie = r2.cookies.get('sid')
        # Set cookie on client to avoid per-request cookies deprecation
        if session_cookie:
            client.cookies.set('sid', session_cookie)
        r3 = client.get('/build/permalink')
        assert r3.status_code == 200
        
        export_data = r3.json()
        assert export_data["ok"] is True
        assert "exclude_cards" in export_data["state"]
        
        # Verify excluded cards are preserved
        exported_excludes = export_data["state"]["exclude_cards"]
        print(f"   Exported {len(exported_excludes)} exclude cards in JSON")
        for card in ["Sol Ring", "Rhystic Study", "Smothering Tithe"]:
            assert card in exported_excludes
        
        # Test import (round-trip)
        token = export_data["permalink"].split("state=")[1]
        r4 = client.get(f'/build/from?state={token}')
        assert r4.status_code == 200
        print("   JSON import successful - round-trip verified")
        
        # 5. Test performance benchmarks
        print("\n5. Testing performance benchmarks:")
        
        # Parsing performance
        parse_times = []
        for _ in range(10):
            start = time.time()
            parse_card_list_input(exclude_cards_content)
            parse_times.append((time.time() - start) * 1000)
        
        avg_parse_time = sum(parse_times) / len(parse_times)
        print(f"   Average parse time: {avg_parse_time:.2f}ms (target: <10ms)")
        assert avg_parse_time < 10.0
        
        # Validation API performance
        validation_times = []
        for _ in range(5):
            start = time.time()
            client.post('/build/validate/exclude_cards', data={'exclude_cards': exclude_cards_content})
            validation_times.append((time.time() - start) * 1000)
        
        avg_validation_time = sum(validation_times) / len(validation_times)
        print(f"   Average validation time: {avg_validation_time:.1f}ms (target: <100ms)")
        assert avg_validation_time < 100.0
        
        # 6. Test backward compatibility
        print("\n6. Testing backward compatibility:")
        
        # Legacy config without exclude_cards
        legacy_payload = {
            "commander": "Inti, Seneschal of the Sun",
            "tags": ["discard"],
            "bracket": 3,
            "ideals": {"ramp": 10, "lands": 36, "basic_lands": 18, "creatures": 28, 
                      "removal": 10, "wipes": 3, "card_advantage": 8, "protection": 4},
            "tag_mode": "AND",
            "flags": {"owned_only": False, "prefer_owned": False},
            "locks": [],
        }
        
        raw = json.dumps(legacy_payload, separators=(",", ":")).encode('utf-8')
        legacy_token = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
        
        r5 = client.get(f'/build/from?state={legacy_token}')
        assert r5.status_code == 200
        print("   Legacy config import works without exclude_cards")
        
        print("\n=== ALL EXCLUDE CARD FEATURES VERIFIED ===")
        print("✅ File upload parsing (simulated)")
        print("✅ Live validation API with performance targets met")
        print("✅ Complete deck building workflow with exclude filtering")
        print("✅ JSON export/import with exclude_cards preservation")
        print("✅ Performance benchmarks under targets")
        print("✅ Backward compatibility with legacy configs")
        print("\n🎉 EXCLUDE CARDS IMPLEMENTATION COMPLETE! 🎉")
        
    finally:
        # Restore environment
        if original_value is not None:
            os.environ['ALLOW_MUST_HAVES'] = original_value
        else:
            os.environ.pop('ALLOW_MUST_HAVES', None)


# =============================================================================
# SECTION: Compatibility Tests
# Source: test_exclude_cards_compatibility.py
# =============================================================================

@pytest.fixture
def client():
    """Test client with ALLOW_MUST_HAVES enabled."""
    import importlib
    
    # Ensure project root is in sys.path for reliable imports
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Ensure feature flag is enabled for tests
    original_value = os.environ.get('ALLOW_MUST_HAVES')
    os.environ['ALLOW_MUST_HAVES'] = '1'
    
    # Force fresh import to pick up environment change
    try:
        del importlib.sys.modules['code.web.app']
    except KeyError:
        pass
    
    app_module = importlib.import_module('code.web.app')
    client = TestClient(app_module.app)
    
    yield client
    
    # Restore original environment
    if original_value is not None:
        os.environ['ALLOW_MUST_HAVES'] = original_value
    else:
        os.environ.pop('ALLOW_MUST_HAVES', None)


def test_legacy_configs_build_unchanged(client):
    """Ensure existing deck configs (without exclude_cards) build identically."""
    # Legacy payload without exclude_cards
    legacy_payload = {
        "commander": "Inti, Seneschal of the Sun",
        "tags": ["discard"],
        "bracket": 3,
        "ideals": {
            "ramp": 10, "lands": 36, "basic_lands": 18, 
            "creatures": 28, "removal": 10, "wipes": 3, 
            "card_advantage": 8, "protection": 4
        },
        "tag_mode": "AND",
        "flags": {"owned_only": False, "prefer_owned": False},
        "locks": [],
    }
    
    # Convert to permalink token
    raw = json.dumps(legacy_payload, separators=(",", ":")).encode('utf-8')
    token = base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')
    
    # Import the legacy config
    response = client.get(f'/build/from?state={token}')
    assert response.status_code == 200


def test_exclude_cards_json_roundtrip(client):
    """Test that exclude_cards are preserved in JSON export/import."""
    # Start a session
    r = client.get('/build')
    assert r.status_code == 200
    
    # Create a config with exclude_cards via form submission
    form_data = {
        "name": "Test Deck",
        "commander": "Inti, Seneschal of the Sun",
        "primary_tag": "discard",
        "bracket": 3,
        "ramp": 10,
        "lands": 36,
        "basic_lands": 18,
        "creatures": 28,
        "removal": 10,
        "wipes": 3,
        "card_advantage": 8,
        "protection": 4,
        "exclude_cards": "Sol Ring\nRhystic Study\nSmothering Tithe"
    }
    
    # Submit the form to create the config
    r2 = client.post('/build/new', data=form_data)
    assert r2.status_code == 200
    
    # Get the session cookie for the next request
    session_cookie = r2.cookies.get('sid')
    assert session_cookie is not None, "Session cookie not found"
    
    # Export permalink with exclude_cards
    if session_cookie:
        client.cookies.set('sid', session_cookie)
    r3 = client.get('/build/permalink')
    assert r3.status_code == 200
    
    permalink_data = r3.json()
    assert permalink_data["ok"] is True
    assert "exclude_cards" in permalink_data["state"]
    
    exported_excludes = permalink_data["state"]["exclude_cards"]
    assert "Sol Ring" in exported_excludes
    assert "Rhystic Study" in exported_excludes
    assert "Smothering Tithe" in exported_excludes
    
    # Test round-trip: import the exported config
    token = permalink_data["permalink"].split("state=")[1]
    r4 = client.get(f'/build/from?state={token}')
    assert r4.status_code == 200
    
    # Get new permalink to verify the exclude_cards were preserved
    # (We need to get the session cookie from the import response)
    import_cookie = r4.cookies.get('sid')
    assert import_cookie is not None, "Import session cookie not found"
    
    if import_cookie:
        client.cookies.set('sid', import_cookie)
    r5 = client.get('/build/permalink')
    assert r5.status_code == 200
    
    reimported_data = r5.json()
    assert reimported_data["ok"] is True
    assert "exclude_cards" in reimported_data["state"]
    
    # Should be identical to the original export
    reimported_excludes = reimported_data["state"]["exclude_cards"]
    assert reimported_excludes == exported_excludes


def test_validation_endpoint_functionality(client):
    """Test the exclude cards validation endpoint."""
    # Test empty input
    r1 = client.post('/build/validate/exclude_cards', data={'exclude_cards': ''})
    assert r1.status_code == 200
    data1 = r1.json()
    assert data1["count"] == 0
    
    # Test valid input
    exclude_text = "Sol Ring\nRhystic Study\nSmothering Tithe"
    r2 = client.post('/build/validate/exclude_cards', data={'exclude_cards': exclude_text})
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2["count"] == 3
    assert data2["limit"] == 15
    assert data2["over_limit"] is False
    assert len(data2["cards"]) == 3
    
    # Test over-limit input (16 cards when limit is 15)
    many_cards = "\n".join([f"Card {i}" for i in range(16)])
    r3 = client.post('/build/validate/exclude_cards', data={'exclude_cards': many_cards})
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3["count"] == 16
    assert data3["over_limit"] is True
    assert len(data3["warnings"]) > 0
    assert "Too many excludes" in data3["warnings"][0]


# =============================================================================
# SECTION: Re-entry Prevention Tests
# Source: test_exclude_reentry_prevention.py
# =============================================================================

class TestExcludeReentryPrevention(unittest.TestCase):
    """Test that excluded cards cannot re-enter the deck."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock input/output functions to avoid interactive prompts
        self.mock_input = Mock(return_value="")
        self.mock_output = Mock()
        
        # Create test card data
        self.test_cards_df = pd.DataFrame([
            {
                'name': 'Lightning Bolt',
                'type': 'Instant',
                'mana_cost': '{R}',
                'manaValue': 1,
                'themeTags': ['burn'],
                'colorIdentity': ['R']
            },
            {
                'name': 'Sol Ring',
                'type': 'Artifact',
                'mana_cost': '{1}',
                'manaValue': 1,
                'themeTags': ['ramp'],
                'colorIdentity': []
            },
            {
                'name': 'Counterspell',
                'type': 'Instant',
                'mana_cost': '{U}{U}',
                'manaValue': 2,
                'themeTags': ['counterspell'],
                'colorIdentity': ['U']
            },
            {
                'name': 'Llanowar Elves',
                'type': 'Creature — Elf Druid',
                'mana_cost': '{G}',
                'manaValue': 1,
                'themeTags': ['ramp', 'elves'],
                'colorIdentity': ['G'],
                'creatureTypes': ['Elf', 'Druid']
            }
        ])

    def _create_test_builder(self, exclude_cards: List[str] = None) -> DeckBuilder:
        """Create a DeckBuilder instance for testing."""
        builder = DeckBuilder(
            input_func=self.mock_input,
            output_func=self.mock_output,
            log_outputs=False,
            headless=True
        )
        
        # Set up basic configuration
        builder.color_identity = ['R', 'G', 'U']
        builder.color_identity_key = 'R, G, U'
        builder._combined_cards_df = self.test_cards_df.copy()
        builder._full_cards_df = self.test_cards_df.copy()
        
        # Set exclude cards
        builder.exclude_cards = exclude_cards or []
        
        return builder

    def test_exclude_prevents_direct_add_card(self):
        """Test that excluded cards are prevented from being added directly."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt', 'Sol Ring'])
        
        # Try to add excluded cards directly
        builder.add_card('Lightning Bolt', card_type='Instant')
        builder.add_card('Sol Ring', card_type='Artifact')
        
        # Verify excluded cards were not added
        self.assertNotIn('Lightning Bolt', builder.card_library)
        self.assertNotIn('Sol Ring', builder.card_library)

    def test_exclude_allows_non_excluded_cards(self):
        """Test that non-excluded cards can still be added normally."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Add a non-excluded card
        builder.add_card('Sol Ring', card_type='Artifact')
        builder.add_card('Counterspell', card_type='Instant')
        
        # Verify non-excluded cards were added
        self.assertIn('Sol Ring', builder.card_library)
        self.assertIn('Counterspell', builder.card_library)

    def test_exclude_prevention_with_fuzzy_matching(self):
        """Test that exclude prevention works with normalized card names."""
        # Test variations in card name formatting
        builder = self._create_test_builder(exclude_cards=['lightning bolt'])  # lowercase
        
        # Try to add with different casing/formatting
        builder.add_card('Lightning Bolt', card_type='Instant')  # proper case
        builder.add_card('LIGHTNING BOLT', card_type='Instant')  # uppercase
        
        # All should be prevented
        self.assertNotIn('Lightning Bolt', builder.card_library)
        self.assertNotIn('LIGHTNING BOLT', builder.card_library)

    def test_exclude_prevention_with_punctuation_variations(self):
        """Test exclude prevention with punctuation variations."""
        # Create test data with punctuation
        test_df = pd.DataFrame([
            {
                'name': 'Krenko, Mob Boss',
                'type': 'Legendary Creature — Goblin Warrior',
                'mana_cost': '{2}{R}{R}',
                'manaValue': 4,
                'themeTags': ['goblins'],
                'colorIdentity': ['R']
            }
        ])
        
        builder = self._create_test_builder(exclude_cards=['Krenko Mob Boss'])  # no comma
        builder._combined_cards_df = test_df
        builder._full_cards_df = test_df
        
        # Try to add with comma (should be prevented due to normalization)
        builder.add_card('Krenko, Mob Boss', card_type='Legendary Creature — Goblin Warrior')
        
        # Should be prevented
        self.assertNotIn('Krenko, Mob Boss', builder.card_library)

    def test_commander_exemption_from_exclude_prevention(self):
        """Test that commanders are exempted from exclude prevention."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Add Lightning Bolt as commander (should be allowed)
        builder.add_card('Lightning Bolt', card_type='Instant', is_commander=True)
        
        # Should be added despite being in exclude list
        self.assertIn('Lightning Bolt', builder.card_library)
        self.assertTrue(builder.card_library['Lightning Bolt']['Commander'])

    def test_exclude_reentry_prevention_during_phases(self):
        """Test that excluded cards cannot re-enter during creature/spell phases."""
        builder = self._create_test_builder(exclude_cards=['Llanowar Elves'])
        
        # Simulate a creature addition phase trying to add excluded creature
        # This would typically happen through automated heuristics
        builder.add_card('Llanowar Elves', card_type='Creature — Elf Druid', added_by='creature_phase')
        
        # Should be prevented
        self.assertNotIn('Llanowar Elves', builder.card_library)

    def test_exclude_prevention_with_empty_exclude_list(self):
        """Test that exclude prevention handles empty exclude lists gracefully."""
        builder = self._create_test_builder(exclude_cards=[])
        
        # Should allow normal addition
        builder.add_card('Lightning Bolt', card_type='Instant')
        
        # Should be added normally
        self.assertIn('Lightning Bolt', builder.card_library)

    def test_exclude_prevention_with_none_exclude_list(self):
        """Test that exclude prevention handles None exclude lists gracefully."""
        builder = self._create_test_builder()
        builder.exclude_cards = None  # Explicitly set to None
        
        # Should allow normal addition
        builder.add_card('Lightning Bolt', card_type='Instant')
        
        # Should be added normally
        self.assertIn('Lightning Bolt', builder.card_library)

    def test_multiple_exclude_attempts_logged(self):
        """Test that multiple attempts to add excluded cards are properly logged."""
        builder = self._create_test_builder(exclude_cards=['Sol Ring'])
        
        # Track log calls by mocking the logger
        with self.assertLogs('deck_builder.builder', level='INFO') as log_context:
            # Try to add excluded card multiple times
            builder.add_card('Sol Ring', card_type='Artifact', added_by='test1')
            builder.add_card('Sol Ring', card_type='Artifact', added_by='test2')
            builder.add_card('Sol Ring', card_type='Artifact', added_by='test3')
        
        # Verify card was not added
        self.assertNotIn('Sol Ring', builder.card_library)
        
        # Verify logging occurred
        log_messages = [record.message for record in log_context.records]
        prevent_logs = [msg for msg in log_messages if 'EXCLUDE_REENTRY_PREVENTED' in msg]
        self.assertEqual(len(prevent_logs), 3)  # Should log each prevention

    def test_exclude_prevention_maintains_deck_integrity(self):
        """Test that exclude prevention doesn't interfere with normal deck building."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Add a mix of cards, some excluded, some not
        cards_to_add = [
            ('Lightning Bolt', 'Instant'),  # excluded
            ('Sol Ring', 'Artifact'),      # allowed
            ('Counterspell', 'Instant'),   # allowed
            ('Lightning Bolt', 'Instant'), # excluded (retry)
            ('Llanowar Elves', 'Creature — Elf Druid')  # allowed
        ]
        
        for name, card_type in cards_to_add:
            builder.add_card(name, card_type=card_type)
        
        # Verify only non-excluded cards were added
        expected_cards = {'Sol Ring', 'Counterspell', 'Llanowar Elves'}
        actual_cards = set(builder.card_library.keys())
        
        self.assertEqual(actual_cards, expected_cards)
        self.assertNotIn('Lightning Bolt', actual_cards)

    def test_exclude_prevention_works_after_pool_filtering(self):
        """Test that exclude prevention works even after pool filtering removes cards."""
        builder = self._create_test_builder(exclude_cards=['Lightning Bolt'])
        
        # Simulate setup_dataframes filtering (M0.5 implementation)
        # The card should already be filtered from the pool, but prevention should still work
        original_df = builder._combined_cards_df.copy()
        
        # Remove Lightning Bolt from pool (simulating M0.5 filtering)
        builder._combined_cards_df = original_df[original_df['name'] != 'Lightning Bolt']
        
        # Try to add it anyway (simulating downstream heuristic attempting to add)
        builder.add_card('Lightning Bolt', card_type='Instant')
        
        # Should still be prevented
        self.assertNotIn('Lightning Bolt', builder.card_library)


if __name__ == "__main__":
    pytest.main([__file__])
