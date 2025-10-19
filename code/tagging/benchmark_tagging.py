"""Benchmark tagging approaches: tag-centric vs card-centric.

Compares performance of:
1. Tag-centric (current): Multiple passes, one per tag type
2. Card-centric (new): Single pass, all tags per card

Usage:
    python code/tagging/benchmark_tagging.py
    
Or in Python:
    from code.tagging.benchmark_tagging import run_benchmark
    run_benchmark()
"""

from __future__ import annotations

import time

import pandas as pd

from file_setup.data_loader import DataLoader
from logging_util import get_logger
from path_util import get_processed_cards_path

logger = get_logger(__name__)


def load_sample_data(sample_size: int = 1000) -> pd.DataFrame:
    """Load a sample of cards for benchmarking.
    
    Args:
        sample_size: Number of cards to sample (default: 1000)
        
    Returns:
        DataFrame with sampled cards
    """
    logger.info(f"Loading {sample_size} cards for benchmark")
    
    all_cards_path = get_processed_cards_path()
    loader = DataLoader()
    
    df = loader.read_cards(all_cards_path, format="parquet")
    
    # Sample random cards (reproducible)
    if len(df) > sample_size:
        df = df.sample(n=sample_size, random_state=42)
    
    # Reset themeTags for fair comparison
    df['themeTags'] = pd.Series([[] for _ in range(len(df))], index=df.index)
    
    logger.info(f"Loaded {len(df)} cards for benchmarking")
    return df


def benchmark_tag_centric(df: pd.DataFrame, iterations: int = 3) -> dict:
    """Benchmark the traditional tag-centric approach.
    
    Simulates the multi-pass approach where each tag function
    iterates through all cards.
    
    Args:
        df: DataFrame to tag
        iterations: Number of times to run (for averaging)
        
    Returns:
        Dict with timing stats
    """
    import re
    
    times = []
    
    for i in range(iterations):
        test_df = df.copy()
        
        # Initialize themeTags
        if 'themeTags' not in test_df.columns:
            test_df['themeTags'] = pd.Series([[] for _ in range(len(test_df))], index=test_df.index)
        
        start = time.perf_counter()
        
        # PASS 1: Ramp tags
        for idx in test_df.index:
            text = str(test_df.at[idx, 'text']).lower()
            if re.search(r'add.*mana|search.*land|ramp', text):
                tags = test_df.at[idx, 'themeTags']
                if not isinstance(tags, list):
                    tags = []
                if 'Ramp' not in tags:
                    tags.append('Ramp')
                test_df.at[idx, 'themeTags'] = tags
        
        # PASS 2: Card draw tags
        for idx in test_df.index:
            text = str(test_df.at[idx, 'text']).lower()
            if re.search(r'draw.*card|card draw', text):
                tags = test_df.at[idx, 'themeTags']
                if not isinstance(tags, list):
                    tags = []
                if 'Card Draw' not in tags:
                    tags.append('Card Draw')
                test_df.at[idx, 'themeTags'] = tags
        
        # PASS 3: Removal tags
        for idx in test_df.index:
            text = str(test_df.at[idx, 'text']).lower()
            if re.search(r'destroy|exile|counter|return.*hand', text):
                tags = test_df.at[idx, 'themeTags']
                if not isinstance(tags, list):
                    tags = []
                for tag in ['Removal', 'Interaction']:
                    if tag not in tags:
                        tags.append(tag)
                test_df.at[idx, 'themeTags'] = tags
        
        # PASS 4: Token tags
        for idx in test_df.index:
            text = str(test_df.at[idx, 'text']).lower()
            if re.search(r'create.*token|token.*creature', text):
                tags = test_df.at[idx, 'themeTags']
                if not isinstance(tags, list):
                    tags = []
                if 'Tokens' not in tags:
                    tags.append('Tokens')
                test_df.at[idx, 'themeTags'] = tags
        
        # PASS 5: Card type tags
        for idx in test_df.index:
            type_line = str(test_df.at[idx, 'type']).lower()
            tags = test_df.at[idx, 'themeTags']
            if not isinstance(tags, list):
                tags = []
            if 'creature' in type_line and 'Creature' not in tags:
                tags.append('Creature')
            if 'artifact' in type_line and 'Artifact' not in tags:
                tags.append('Artifact')
            test_df.at[idx, 'themeTags'] = tags
        
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        
        logger.info(f"Tag-centric iteration {i+1}/{iterations}: {elapsed:.3f}s")
    
    return {
        'approach': 'tag-centric',
        'iterations': iterations,
        'times': times,
        'mean': sum(times) / len(times),
        'min': min(times),
        'max': max(times),
    }


def benchmark_card_centric(df: pd.DataFrame, iterations: int = 3) -> dict:
    """Benchmark the new card-centric approach.
    
    Args:
        df: DataFrame to tag
        iterations: Number of times to run (for averaging)
        
    Returns:
        Dict with timing stats
    """
    from tagging.tagger_card_centric import tag_all_cards_single_pass
    
    times = []
    
    for i in range(iterations):
        test_df = df.copy()
        
        start = time.perf_counter()
        
        tag_all_cards_single_pass(test_df)
        
        elapsed = time.perf_counter() - start
        times.append(elapsed)
        
        logger.info(f"Card-centric iteration {i+1}/{iterations}: {elapsed:.3f}s")
    
    return {
        'approach': 'card-centric',
        'iterations': iterations,
        'times': times,
        'mean': sum(times) / len(times),
        'min': min(times),
        'max': max(times),
    }


def run_benchmark(sample_sizes: list[int] = [100, 500, 1000, 5000]) -> None:
    """Run comprehensive benchmark comparing both approaches.
    
    Args:
        sample_sizes: List of dataset sizes to test
    """
    print("\n" + "="*80)
    print("TAGGING APPROACH BENCHMARK")
    print("="*80)
    print("\nComparing:")
    print("  1. Tag-centric (current): Multiple passes, one per tag type")
    print("  2. Card-centric (new):    Single pass, all tags per card")
    print()
    
    results = []
    
    for size in sample_sizes:
        print(f"\n{'─'*80}")
        print(f"Testing with {size:,} cards...")
        print(f"{'─'*80}")
        
        df = load_sample_data(sample_size=size)
        
        # Benchmark tag-centric
        print("\n▶ Tag-centric approach:")
        tag_centric_result = benchmark_tag_centric(df, iterations=3)
        print(f"  Mean: {tag_centric_result['mean']:.3f}s")
        print(f"  Range: {tag_centric_result['min']:.3f}s - {tag_centric_result['max']:.3f}s")
        
        # Benchmark card-centric
        print("\n▶ Card-centric approach:")
        card_centric_result = benchmark_card_centric(df, iterations=3)
        print(f"  Mean: {card_centric_result['mean']:.3f}s")
        print(f"  Range: {card_centric_result['min']:.3f}s - {card_centric_result['max']:.3f}s")
        
        # Compare
        speedup = tag_centric_result['mean'] / card_centric_result['mean']
        winner = "Card-centric" if speedup > 1 else "Tag-centric"
        
        print(f"\n{'─'*40}")
        if speedup > 1:
            print(f"✓ {winner} is {speedup:.2f}x FASTER")
        else:
            print(f"✓ {winner} is {1/speedup:.2f}x FASTER")
        print(f"{'─'*40}")
        
        results.append({
            'size': size,
            'tag_centric_mean': tag_centric_result['mean'],
            'card_centric_mean': card_centric_result['mean'],
            'speedup': speedup,
            'winner': winner,
        })
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\n{'Size':<10} {'Tag-Centric':<15} {'Card-Centric':<15} {'Speedup':<10} {'Winner':<15}")
    print("─" * 80)
    
    for r in results:
        print(f"{r['size']:<10,} {r['tag_centric_mean']:<15.3f} {r['card_centric_mean']:<15.3f} {r['speedup']:<10.2f}x {r['winner']:<15}")
    
    # Overall recommendation
    avg_speedup = sum(r['speedup'] for r in results) / len(results)
    print("\n" + "="*80)
    if avg_speedup > 1:
        print(f"RECOMMENDATION: Use CARD-CENTRIC (avg {avg_speedup:.2f}x faster)")
    else:
        print(f"RECOMMENDATION: Use TAG-CENTRIC (avg {1/avg_speedup:.2f}x faster)")
    print("="*80 + "\n")


if __name__ == "__main__":
    run_benchmark()
