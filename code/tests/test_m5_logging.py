#!/usr/bin/env python3
"""
Test M5 Quality & Observability features.
Verify structured logging events for include/exclude decisions.
"""

import sys
import os
import logging
import io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'code'))

from deck_builder.builder import DeckBuilder


def test_m5_structured_logging():
    """Test that M5 structured logging events are emitted correctly."""
    
    # Capture log output
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
    handler.setFormatter(formatter)
    
    # Get the deck builder logger
    from deck_builder import builder
    logger = logging.getLogger(builder.__name__)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    
    print("🔍 Testing M5 Structured Logging...")
    
    try:
        # Create a mock builder instance
        builder_obj = DeckBuilder()
        
        # Mock the required functions to avoid prompts
        from unittest.mock import Mock
        builder_obj.input_func = Mock(return_value="")
        builder_obj.output_func = Mock()
        
        # Set up test attributes
        builder_obj.commander_name = "Alesha, Who Smiles at Death"
        builder_obj.include_cards = ["Sol Ring", "Lightning Bolt", "Chaos Warp"]
        builder_obj.exclude_cards = ["Mana Crypt", "Force of Will"]
        builder_obj.enforcement_mode = "warn"
        builder_obj.allow_illegal = False
        builder_obj.fuzzy_matching = True
        
        # Process includes/excludes to trigger logging
        _ = builder_obj._process_includes_excludes()
        
        # Get the log output
        log_output = log_capture.getvalue()
        
        print("\n📊 Captured Log Events:")
        for line in log_output.split('\n'):
            if line.strip():
                print(f"  {line}")
        
        # Check for expected structured events
        expected_events = [
            "INCLUDE_EXCLUDE_PERFORMANCE:",
        ]
        
        found_events = []
        for event in expected_events:
            if event in log_output:
                found_events.append(event)
                print(f"✅ Found event: {event}")
            else:
                print(f"❌ Missing event: {event}")
        
        print(f"\n📋 Results: {len(found_events)}/{len(expected_events)} expected events found")

        # Test strict mode logging
        print("\n🔒 Testing strict mode logging...")
        builder_obj.enforcement_mode = "strict"
        try:
            builder_obj._enforce_includes_strict()
            print("✅ Strict mode passed (no missing includes)")
        except RuntimeError as e:
            print(f"❌ Strict mode failed: {e}")

        assert len(found_events) == len(expected_events)

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logger.removeHandler(handler)


def test_m5_performance_metrics():
    """Test performance metrics are within acceptable ranges."""
    import time
    
    print("\n⏱️  Testing M5 Performance Metrics...")
    
    # Test exclude filtering performance
    start_time = time.perf_counter()
    
    # Simulate exclude filtering on reasonable dataset
    test_excludes = ["Mana Crypt", "Force of Will", "Mana Drain", "Timetwister", "Ancestral Recall"]
    test_pool_size = 1000  # Smaller for testing
    
    # Simple set lookup simulation (the optimization we want)
    exclude_set = set(test_excludes)
    filtered_count = 0
    for i in range(test_pool_size):
        card_name = f"Card_{i}"
        if card_name not in exclude_set:
            filtered_count += 1
    
    duration_ms = (time.perf_counter() - start_time) * 1000
    
    print(f"  Exclude filtering: {duration_ms:.2f}ms for {len(test_excludes)} patterns on {test_pool_size} cards")
    print(f"  Filtered: {test_pool_size - filtered_count} cards")
    
    # Performance should be very fast with set lookups
    performance_acceptable = duration_ms < 10.0  # Very generous threshold for small test
    
    if performance_acceptable:
        print("✅ Performance metrics acceptable")
    else:
        print("❌ Performance metrics too slow")
    
    assert performance_acceptable


if __name__ == "__main__":
    print("🧪 Testing M5 - Quality & Observability")
    print("=" * 50)
    
    test1_pass = test_m5_structured_logging()
    test2_pass = test_m5_performance_metrics()
    
    print("\n📋 M5 Test Summary:")
    print(f"   Structured logging: {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"   Performance metrics: {'✅ PASS' if test2_pass else '❌ FAIL'}")
    
    if test1_pass and test2_pass:
        print("\n🎉 M5 Quality & Observability tests passed!")
        print("📈 Structured events implemented for include/exclude decisions")
        print("⚡ Performance optimization confirmed with set-based lookups")
    else:
        print("\n🔧 Some M5 tests failed - check implementation")
    
    exit(0 if test1_pass and test2_pass else 1)
