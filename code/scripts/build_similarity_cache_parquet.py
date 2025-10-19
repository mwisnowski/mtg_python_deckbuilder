"""
Build similarity cache for all cards in the database using Parquet format.

Pre-computes and stores similarity calculations for ~29k cards to improve
card detail page performance from 2-6s down to <500ms.

NOTE: This script assumes card data and tagging are already complete.
Run setup and tagging separately before building the cache.

Usage:
    python -m code.scripts.build_similarity_cache_parquet [--parallel] [--checkpoint-interval 100]
    
Options:
    --parallel              Enable parallel processing (faster but uses more CPU)
    --checkpoint-interval   Save cache every N cards (default: 100)
    --force                 Rebuild cache even if it exists
    --dry-run               Calculate without saving (for testing)
    --workers N             Number of parallel workers (default: auto-detect)
"""

import argparse
import logging
import sys
import time
import pandas as pd
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[2]
sys.path.insert(0, str(project_root))

from code.web.services.card_similarity import CardSimilarity
from code.web.services.similarity_cache import SimilarityCache, get_cache

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Shared data for worker processes (passed during initialization, not reloaded per worker)
_shared_cards_df = None
_shared_theme_frequencies = None
_shared_cleaned_tags = None
_worker_similarity = None


def _init_worker(cards_df_pickled: bytes, theme_frequencies: dict, cleaned_tags: dict):
    """
    Initialize worker process with shared data.
    Called once when each worker process starts.

    Args:
        cards_df_pickled: Pickled DataFrame of all cards
        theme_frequencies: Pre-computed theme frequency dict
        cleaned_tags: Pre-computed cleaned tags cache
    """
    import pickle
    import logging

    global _shared_cards_df, _shared_theme_frequencies, _shared_cleaned_tags, _worker_similarity

    # Unpickle shared data once per worker
    _shared_cards_df = pickle.loads(cards_df_pickled)
    _shared_theme_frequencies = theme_frequencies
    _shared_cleaned_tags = cleaned_tags

    # Create worker-level CardSimilarity instance with shared data
    _worker_similarity = CardSimilarity(cards_df=_shared_cards_df)

    # Override pre-computed data to avoid recomputation
    _worker_similarity.theme_frequencies = _shared_theme_frequencies
    _worker_similarity.cleaned_tags_cache = _shared_cleaned_tags

    # Suppress verbose logging in workers
    logging.getLogger("card_similarity").setLevel(logging.WARNING)


def calculate_similarity_for_card(args: tuple) -> tuple[str, list[dict], bool]:
    """
    Calculate similarity for a single card (worker function for parallel processing).

    Args:
        args: Tuple of (card_name, threshold, min_results, limit)

    Returns:
        Tuple of (card_name, similar_cards, success)
    """
    card_name, threshold, min_results, limit = args

    try:
        # Use the global worker-level CardSimilarity instance
        global _worker_similarity
        if _worker_similarity is None:
            # Fallback if initializer wasn't called (shouldn't happen)
            _worker_similarity = CardSimilarity()

        # Calculate without using cache (we're building it)
        similar_cards = _worker_similarity.find_similar(
            card_name=card_name,
            threshold=threshold,
            min_results=min_results,
            limit=limit,
            adaptive=True,
            use_cache=False,
        )

        return card_name, similar_cards, True

    except Exception as e:
        logger.error(f"Failed to calculate similarity for '{card_name}': {e}")
        return card_name, [], False


def _add_results_to_cache(cache_df: pd.DataFrame, card_name: str, similar_cards: list[dict]) -> pd.DataFrame:
    """
    Add similarity results for a card to the cache DataFrame.

    Args:
        cache_df: Existing cache DataFrame
        card_name: Name of the card
        similar_cards: List of similar cards with scores

    Returns:
        Updated DataFrame
    """
    # Build new rows
    new_rows = []
    for rank, card in enumerate(similar_cards):
        new_rows.append({
            "card_name": card_name,
            "similar_name": card["name"],
            "similarity": card["similarity"],
            "edhrecRank": card.get("edhrecRank", float("inf")),
            "rank": rank,
        })

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        cache_df = pd.concat([cache_df, new_df], ignore_index=True)

    return cache_df


def build_cache(
    parallel: bool = False,
    workers: int | None = None,
    checkpoint_interval: int = 100,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Build similarity cache for all cards.
    
    NOTE: Assumes card data (card_files/processed/all_cards.parquet) and tagged data already exist.
    Run setup and tagging separately before building cache.

    Args:
        parallel: Enable parallel processing
        workers: Number of parallel workers (None = auto-detect)
        checkpoint_interval: Save cache every N cards
        force: Rebuild even if cache exists
        dry_run: Calculate without saving
    """
    logger.info("=" * 80)
    logger.info("Similarity Cache Builder (Parquet Edition)")
    logger.info("=" * 80)
    logger.info("")

    # Initialize cache
    cache = get_cache()

    # Quick check for complete cache - if metadata says build is done, exit
    if not force and cache.cache_path.exists() and not dry_run:
        metadata = cache._metadata or {}
        is_complete = metadata.get("build_complete", False)
        
        if is_complete:
            stats = cache.get_stats()
            logger.info(f"Cache already complete with {stats['total_cards']:,} cards")
            logger.info("Use --force to rebuild")
            return
        else:
            stats = cache.get_stats()
            logger.info(f"Resuming incomplete cache with {stats['total_cards']:,} cards")

    if dry_run:
        logger.info("DRY RUN MODE - No changes will be saved")
        logger.info("")

    # Initialize similarity engine
    logger.info("Initializing similarity engine...")
    similarity = CardSimilarity()
    total_cards = len(similarity.cards_df)
    logger.info(f"Loaded {total_cards:,} cards")
    logger.info("")

    # Filter out low-value lands (single-sided with <3 tags)
    df = similarity.cards_df
    df["is_land"] = df["type"].str.contains("Land", case=False, na=False)
    df["is_multifaced"] = df["layout"].str.lower().isin(["modal_dfc", "transform", "reversible_card", "double_faced_token"])
    df["tag_count"] = df["themeTags"].apply(lambda x: len(x.split("|")) if pd.notna(x) and x else 0)

    # Keep cards that are either:
    # 1. Not lands, OR
    # 2. Multi-faced lands, OR
    # 3. Single-sided lands with >= 3 tags
    keep_mask = (~df["is_land"]) | (df["is_multifaced"]) | (df["is_land"] & (df["tag_count"] >= 3))

    card_names = df[keep_mask]["name"].tolist()
    skipped_lands = (~keep_mask & df["is_land"]).sum()

    logger.info(f"Filtered out {skipped_lands} low-value lands (single-sided with <3 tags)")
    logger.info(f"Processing {len(card_names):,} cards ({len(card_names)/total_cards*100:.1f}% of total)")
    logger.info("")

    # Configuration for similarity calculation
    threshold = 0.8
    min_results = 3
    limit = 20  # Cache up to 20 similar cards per card for variety

    # Initialize cache data structure - try to load existing for resume
    existing_cache_df = cache.load_cache()
    already_processed = set()

    if len(existing_cache_df) > 0 and not dry_run:
        # Resume from checkpoint - keep existing data
        cache_df = existing_cache_df
        already_processed = set(existing_cache_df["card_name"].unique())
        logger.info(f"Resuming from checkpoint with {len(already_processed):,} cards already processed")

        # Setup metadata
        metadata = cache._metadata or cache._empty_metadata()
    else:
        # Start fresh
        cache_df = cache._empty_cache_df()
        metadata = cache._empty_metadata()
        metadata["build_date"] = datetime.now().isoformat()
        metadata["threshold"] = threshold
        metadata["min_results"] = min_results

    # Track stats
    start_time = time.time()
    processed = len(already_processed)  # Start count from checkpoint
    failed = 0
    checkpoint_count = 0

    try:
        if parallel:
            # Parallel processing - use available CPU cores
            import os
            import pickle

            if workers is not None:
                max_workers = max(1, workers)  # User-specified, minimum 1
                logger.info(f"Using {max_workers} worker processes (user-specified)")
            else:
                cpu_count = os.cpu_count() or 4
                # Use CPU count - 1 to leave one core for system, minimum 4
                max_workers = max(4, cpu_count - 1)
                logger.info(f"Detected {cpu_count} CPUs, using {max_workers} worker processes")

            # Prepare shared data (pickle DataFrame once, share with all workers)
            logger.info("Preparing shared data for workers...")
            cards_df_pickled = pickle.dumps(similarity.cards_df)
            theme_frequencies = similarity.theme_frequencies.copy()
            cleaned_tags = similarity.cleaned_tags_cache.copy()
            logger.info(f"Shared data prepared: {len(cards_df_pickled):,} bytes (DataFrame), "
                       f"{len(theme_frequencies)} themes, {len(cleaned_tags)} cleaned tag sets")

            # Prepare arguments for cards not yet processed
            cards_to_process = [name for name in card_names if name not in already_processed]
            logger.info(f"Cards to process: {len(cards_to_process):,} (skipping {len(already_processed):,} already done)")

            card_args = [(name, threshold, min_results, limit) for name in cards_to_process]

            with ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=_init_worker,
                initargs=(cards_df_pickled, theme_frequencies, cleaned_tags)
            ) as executor:
                # Submit all tasks
                future_to_card = {
                    executor.submit(calculate_similarity_for_card, args): args[0]
                    for args in card_args
                }

                # Process results as they complete
                for future in as_completed(future_to_card):
                    card_name, similar_cards, success = future.result()

                    if success:
                        cache_df = _add_results_to_cache(cache_df, card_name, similar_cards)
                        processed += 1
                    else:
                        failed += 1

                    # Progress reporting
                    total_to_process = len(card_names)
                    if processed % 100 == 0:
                        elapsed = time.time() - start_time
                        # Calculate rate based on cards processed THIS session
                        cards_this_session = processed - len(already_processed)
                        rate = cards_this_session / elapsed if elapsed > 0 else 0
                        cards_remaining = total_to_process - processed
                        eta = cards_remaining / rate if rate > 0 else 0
                        logger.info(
                            f"Progress: {processed}/{total_to_process} "
                            f"({processed/total_to_process*100:.1f}%) - "
                            f"Rate: {rate:.1f} cards/sec - "
                            f"ETA: {eta/60:.1f} min"
                        )

                    # Checkpoint save
                    if not dry_run and processed % checkpoint_interval == 0:
                        checkpoint_count += 1
                        cache.save_cache(cache_df, metadata)
                        logger.info(f"Checkpoint {checkpoint_count}: Saved cache with {processed:,} cards")

        else:
            # Serial processing - skip already processed cards
            cards_to_process = [name for name in card_names if name not in already_processed]
            logger.info(f"Cards to process: {len(cards_to_process):,} (skipping {len(already_processed):,} already done)")

            for i, card_name in enumerate(cards_to_process, start=1):
                try:
                    similar_cards = similarity.find_similar(
                        card_name=card_name,
                        threshold=threshold,
                        min_results=min_results,
                        limit=limit,
                        adaptive=True,
                        use_cache=False,
                    )

                    cache_df = _add_results_to_cache(cache_df, card_name, similar_cards)
                    processed += 1

                except Exception as e:
                    logger.error(f"Failed to process '{card_name}': {e}")
                    failed += 1

                # Progress reporting
                if i % 100 == 0:
                    elapsed = time.time() - start_time
                    rate = i / elapsed if elapsed > 0 else 0
                    cards_remaining = len(card_names) - i
                    eta = cards_remaining / rate if rate > 0 else 0
                    logger.info(
                        f"Progress: {i}/{len(card_names)} "
                        f"({i/len(card_names)*100:.1f}%) - "
                        f"Rate: {rate:.1f} cards/sec - "
                        f"ETA: {eta/60:.1f} min"
                    )

                # Checkpoint save
                if not dry_run and i % checkpoint_interval == 0:
                    checkpoint_count += 1
                    cache.save_cache(cache_df, metadata)
                    logger.info(f"Checkpoint {checkpoint_count}: Saved cache with {i:,} cards")

        # Final save
        if not dry_run:
            metadata["last_updated"] = datetime.now().isoformat()
            metadata["build_complete"] = True
            cache.save_cache(cache_df, metadata)

        # Summary
        elapsed = time.time() - start_time
        logger.info("")
        logger.info("=" * 80)
        logger.info("Build Complete")
        logger.info("=" * 80)
        logger.info(f"Total time: {elapsed/60:.2f} minutes")
        logger.info(f"Cards processed: {processed:,}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Checkpoints saved: {checkpoint_count}")

        if processed > 0:
            logger.info(f"Average rate: {processed/elapsed:.2f} cards/sec")

        if not dry_run:
            stats = cache.get_stats()
            logger.info(f"Cache file size: {stats.get('file_size_mb', 0):.2f} MB")
            logger.info(f"Cache location: {cache.cache_path}")

    except KeyboardInterrupt:
        logger.warning("\nBuild interrupted by user")

        # Save partial cache
        if not dry_run and len(cache_df) > 0:
            metadata["last_updated"] = datetime.now().isoformat()
            cache.save_cache(cache_df, metadata)
            logger.info(f"Saved partial cache with {processed:,} cards")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Build similarity cache for all cards (Parquet format)"
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel processing",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: auto-detect)",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=100,
        help="Save cache every N cards (default: 100)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild cache even if it exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calculate without saving (for testing)",
    )

    args = parser.parse_args()

    build_cache(
        parallel=args.parallel,
        workers=args.workers,
        checkpoint_interval=args.checkpoint_interval,
        force=args.force,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
