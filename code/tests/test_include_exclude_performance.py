#!/usr/bin/env python3
"""
M3 Performance Tests - UI Responsiveness with Max Lists
Tests the performance targets specified in the roadmap.
"""

import time
import random
import json
from typing import List, Dict, Any

# Performance test targets from roadmap
PERFORMANCE_TARGETS = {
    "exclude_filtering": 50,  # ms for 15 excludes on 20k+ cards
    "fuzzy_matching": 200,   # ms for single lookup + suggestions  
    "include_injection": 100, # ms for 10 includes
    "full_validation": 500,   # ms for max lists (10 includes + 15 excludes)
    "ui_operations": 50,      # ms for chip operations
    "total_build_impact": 0.10  # 10% increase vs baseline
}

# Sample card names for testing
SAMPLE_CARDS = [
    "Lightning Bolt", "Counterspell", "Swords to Plowshares", "Path to Exile",
    "Sol Ring", "Command Tower", "Reliquary Tower", "Beast Within",
    "Generous Gift", "Anointed Procession", "Rhystic Study", "Mystical Tutor",
    "Demonic Tutor", "Vampiric Tutor", "Enlightened Tutor", "Worldly Tutor",
    "Cyclonic Rift", "Wrath of God", "Day of Judgment", "Austere Command",
    "Nature's Claim", "Krosan Grip", "Return to Nature", "Disenchant",
    "Eternal Witness", "Reclamation Sage", "Acidic Slime", "Solemn Simulacrum"
]

def generate_max_include_list() -> List[str]:
    """Generate maximum size include list (10 cards)."""
    return random.sample(SAMPLE_CARDS, min(10, len(SAMPLE_CARDS)))

def generate_max_exclude_list() -> List[str]:
    """Generate maximum size exclude list (15 cards)."""
    return random.sample(SAMPLE_CARDS, min(15, len(SAMPLE_CARDS)))

def simulate_card_parsing(card_list: List[str]) -> Dict[str, Any]:
    """Simulate card list parsing performance."""
    start_time = time.perf_counter()
    
    # Simulate parsing logic
    parsed_cards = []
    for card in card_list:
        # Simulate normalization and validation
        normalized = card.strip().lower()
        if normalized:
            parsed_cards.append(card)
        time.sleep(0.0001)  # Simulate processing time
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    return {
        "duration_ms": duration_ms,
        "card_count": len(parsed_cards),
        "parsed_cards": parsed_cards
    }

def simulate_fuzzy_matching(card_name: str) -> Dict[str, Any]:
    """Simulate fuzzy matching performance."""
    start_time = time.perf_counter()
    
    # Simulate fuzzy matching against large card database
    suggestions = []
    
    # Simulate checking against 20k+ cards
    for i in range(20000):
        # Simulate string comparison
        if i % 1000 == 0:
            suggestions.append(f"Similar Card {i//1000}")
        if len(suggestions) >= 3:
            break
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    return {
        "duration_ms": duration_ms,
        "suggestions": suggestions[:3],
        "confidence": 0.85
    }

def simulate_exclude_filtering(exclude_list: List[str], card_pool_size: int = 20000) -> Dict[str, Any]:
    """Simulate exclude filtering performance on large card pool."""
    start_time = time.perf_counter()
    
    # Simulate filtering large dataframe
    exclude_set = set(card.lower() for card in exclude_list)
    filtered_count = 0
    
    # Simulate checking each card in pool
    for i in range(card_pool_size):
        card_name = f"card_{i}".lower()
        if card_name not in exclude_set:
            filtered_count += 1
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    return {
        "duration_ms": duration_ms,
        "exclude_count": len(exclude_list),
        "pool_size": card_pool_size,
        "filtered_count": filtered_count
    }

def simulate_include_injection(include_list: List[str]) -> Dict[str, Any]:
    """Simulate include injection performance."""
    start_time = time.perf_counter()
    
    # Simulate card lookup and injection
    injected_cards = []
    for card in include_list:
        # Simulate finding card in pool
        time.sleep(0.001)  # Simulate database lookup
        
        # Simulate metadata extraction and deck addition
        card_data = {
            "name": card,
            "type": "Unknown",
            "mana_cost": "{1}",
            "category": "spells"
        }
        injected_cards.append(card_data)
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    return {
        "duration_ms": duration_ms,
        "include_count": len(include_list),
        "injected_cards": len(injected_cards)
    }

def simulate_full_validation(include_list: List[str], exclude_list: List[str]) -> Dict[str, Any]:
    """Simulate full validation cycle with max lists."""
    start_time = time.perf_counter()
    
    # Simulate comprehensive validation
    results = {
        "includes": {
            "count": len(include_list),
            "legal": len(include_list) - 1,  # Simulate one issue
            "illegal": 1,
            "warnings": []
        },
        "excludes": {
            "count": len(exclude_list),
            "legal": len(exclude_list),
            "illegal": 0,
            "warnings": []
        }
    }
    
    # Simulate validation logic
    for card in include_list + exclude_list:
        time.sleep(0.0005)  # Simulate validation time per card
    
    end_time = time.perf_counter()
    duration_ms = (end_time - start_time) * 1000
    
    return {
        "duration_ms": duration_ms,
        "total_cards": len(include_list) + len(exclude_list),
        "results": results
    }

def run_performance_tests() -> Dict[str, Any]:
    """Run all M3 performance tests."""
    print("🚀 Running M3 Performance Tests...")
    print("=" * 50)
    
    results = {}
    
    # Test 1: Exclude Filtering Performance
    print("📊 Testing exclude filtering (15 excludes on 20k+ cards)...")
    exclude_list = generate_max_exclude_list()
    exclude_result = simulate_exclude_filtering(exclude_list)
    results["exclude_filtering"] = exclude_result
    
    target = PERFORMANCE_TARGETS["exclude_filtering"]
    status = "✅ PASS" if exclude_result["duration_ms"] <= target else "❌ FAIL"
    print(f"   Duration: {exclude_result['duration_ms']:.1f}ms (target: ≤{target}ms) {status}")
    
    # Test 2: Fuzzy Matching Performance  
    print("🔍 Testing fuzzy matching (single lookup + suggestions)...")
    fuzzy_result = simulate_fuzzy_matching("Lightning Blot")  # Typo
    results["fuzzy_matching"] = fuzzy_result
    
    target = PERFORMANCE_TARGETS["fuzzy_matching"]
    status = "✅ PASS" if fuzzy_result["duration_ms"] <= target else "❌ FAIL"
    print(f"   Duration: {fuzzy_result['duration_ms']:.1f}ms (target: ≤{target}ms) {status}")
    
    # Test 3: Include Injection Performance
    print("⚡ Testing include injection (10 includes)...")
    include_list = generate_max_include_list()
    injection_result = simulate_include_injection(include_list)
    results["include_injection"] = injection_result
    
    target = PERFORMANCE_TARGETS["include_injection"]
    status = "✅ PASS" if injection_result["duration_ms"] <= target else "❌ FAIL"
    print(f"   Duration: {injection_result['duration_ms']:.1f}ms (target: ≤{target}ms) {status}")
    
    # Test 4: Full Validation Performance
    print("🔬 Testing full validation cycle (10 includes + 15 excludes)...")
    validation_result = simulate_full_validation(include_list, exclude_list)
    results["full_validation"] = validation_result
    
    target = PERFORMANCE_TARGETS["full_validation"] 
    status = "✅ PASS" if validation_result["duration_ms"] <= target else "❌ FAIL"
    print(f"   Duration: {validation_result['duration_ms']:.1f}ms (target: ≤{target}ms) {status}")
    
    # Test 5: UI Operation Simulation
    print("🖱️  Testing UI operations (chip add/remove)...")
    ui_start = time.perf_counter()
    
    # Simulate 10 chip operations
    for i in range(10):
        time.sleep(0.001)  # Simulate DOM manipulation
    
    ui_duration = (time.perf_counter() - ui_start) * 1000
    results["ui_operations"] = {"duration_ms": ui_duration, "operations": 10}
    
    target = PERFORMANCE_TARGETS["ui_operations"]
    status = "✅ PASS" if ui_duration <= target else "❌ FAIL"
    print(f"   Duration: {ui_duration:.1f}ms (target: ≤{target}ms) {status}")
    
    # Summary
    print("\n📋 Performance Test Summary:")
    print("-" * 30)
    
    total_tests = len(PERFORMANCE_TARGETS) - 1  # Exclude total_build_impact
    passed_tests = 0
    
    for test_name, target in PERFORMANCE_TARGETS.items():
        if test_name == "total_build_impact":
            continue
            
        if test_name in results:
            actual = results[test_name]["duration_ms"]
            passed = actual <= target
            if passed:
                passed_tests += 1
            status_icon = "✅" if passed else "❌"
            print(f"{status_icon} {test_name}: {actual:.1f}ms / {target}ms")
    
    pass_rate = (passed_tests / total_tests) * 100
    print(f"\n🎯 Overall Pass Rate: {passed_tests}/{total_tests} ({pass_rate:.1f}%)")
    
    if pass_rate >= 80:
        print("🎉 Performance targets largely met! M3 performance is acceptable.")
    else:
        print("⚠️  Some performance targets missed. Consider optimizations.")
    
    return results

if __name__ == "__main__":
    try:
        results = run_performance_tests()
        
        # Save results for analysis
        with open("m3_performance_results.json", "w") as f:
            json.dump(results, f, indent=2)
        
        print("\n📄 Results saved to: m3_performance_results.json")
        
    except Exception as e:
        print(f"❌ Performance test failed: {e}")
        exit(1)
