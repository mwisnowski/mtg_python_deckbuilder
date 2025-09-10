"""
Exclude Cards Performance Tests

Ensures that exclude filtering doesn't create significant performance
regressions and meets the specified benchmarks for parsing, filtering,
and validation operations.
"""
import time
import pytest
from deck_builder.include_exclude_utils import parse_card_list_input


def test_card_parsing_speed():
    """Test that exclude card parsing is fast."""
    # Create a list of 15 cards (max excludes)
    exclude_cards_text = "\n".join([
        "Sol Ring", "Rhystic Study", "Smothering Tithe", "Lightning Bolt",
        "Counterspell", "Swords to Plowshares", "Path to Exile",
        "Mystical Tutor", "Demonic Tutor", "Vampiric Tutor",
        "Mana Crypt", "Chrome Mox", "Mox Diamond", "Mox Opal", "Lotus Petal"
    ])
    
    # Time the parsing operation
    start_time = time.time()
    for _ in range(100):  # Run 100 times to get a meaningful measurement
        result = parse_card_list_input(exclude_cards_text)
    end_time = time.time()
    
    # Should complete 100 parses in well under 1 second
    total_time = end_time - start_time
    avg_time_per_parse = total_time / 100
    
    assert len(result) == 15
    assert avg_time_per_parse < 0.01  # Less than 10ms per parse (very generous)
    print(f"Average parse time: {avg_time_per_parse*1000:.2f}ms")


def test_large_cardpool_filtering_speed():
    """Simulate exclude filtering performance on a large card pool."""
    # Create a mock dataframe-like structure to simulate filtering
    mock_card_pool_size = 20000  # Typical large card pool
    exclude_list = [
        "Sol Ring", "Rhystic Study", "Smothering Tithe", "Lightning Bolt",
        "Counterspell", "Swords to Plowshares", "Path to Exile",
        "Mystical Tutor", "Demonic Tutor", "Vampiric Tutor",
        "Mana Crypt", "Chrome Mox", "Mox Diamond", "Mox Opal", "Lotus Petal"
    ]
    
    # Simulate the filtering operation (set-based lookup)
    exclude_set = set(exclude_list)
    
    # Create mock card names
    mock_cards = [f"Card {i}" for i in range(mock_card_pool_size)]
    # Add a few cards that will be excluded
    mock_cards.extend(exclude_list)
    
    # Time the filtering operation
    start_time = time.time()
    filtered_cards = [card for card in mock_cards if card not in exclude_set]
    end_time = time.time()
    
    filter_time = end_time - start_time
    
    # Should complete filtering in well under 50ms (our target)
    assert filter_time < 0.050  # 50ms
    print(f"Filtering {len(mock_cards)} cards took {filter_time*1000:.2f}ms")
    
    # Verify filtering worked
    for excluded_card in exclude_list:
        assert excluded_card not in filtered_cards


def test_validation_api_response_time():
    """Test validation endpoint response time."""
    import importlib
    import os
    import sys
    from starlette.testclient import TestClient
    
    # Ensure project root is in sys.path for reliable imports
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    
    # Enable feature flag
    original_value = os.environ.get('ALLOW_MUST_HAVES')
    os.environ['ALLOW_MUST_HAVES'] = '1'
    
    try:
        # Fresh import
        try:
            del importlib.sys.modules['code.web.app']
        except KeyError:
            pass
        
        app_module = importlib.import_module('code.web.app')
        client = TestClient(app_module.app)
        
        # Test data
        exclude_text = "\n".join([
            "Sol Ring", "Rhystic Study", "Smothering Tithe", "Lightning Bolt",
            "Counterspell", "Swords to Plowshares", "Path to Exile",
            "Mystical Tutor", "Demonic Tutor", "Vampiric Tutor"
        ])
        
        # Time the validation request
        start_time = time.time()
        response = client.post('/build/validate/exclude_cards', 
                             data={'exclude_cards': exclude_text})
        end_time = time.time()
        
        response_time = end_time - start_time
        
        # Should respond in under 100ms (our target)
        assert response_time < 0.100  # 100ms
        assert response.status_code == 200
        
        print(f"Validation endpoint response time: {response_time*1000:.2f}ms")
        
    finally:
        # Restore environment
        if original_value is not None:
            os.environ['ALLOW_MUST_HAVES'] = original_value
        else:
            os.environ.pop('ALLOW_MUST_HAVES', None)


@pytest.mark.parametrize("exclude_count", [0, 5, 10, 15])
def test_parsing_scales_with_list_size(exclude_count):
    """Test that performance scales reasonably with number of excludes."""
    exclude_cards = [f"Exclude Card {i}" for i in range(exclude_count)]
    exclude_text = "\n".join(exclude_cards)
    
    start_time = time.time()
    result = parse_card_list_input(exclude_text)
    end_time = time.time()
    
    parse_time = end_time - start_time
    
    # Even with maximum excludes, should be very fast
    assert parse_time < 0.005  # 5ms
    assert len(result) == exclude_count
    
    print(f"Parse time for {exclude_count} excludes: {parse_time*1000:.2f}ms")
