"""
Card similarity service using Jaccard index on theme tags.

Provides similarity scoring between cards based on theme tag overlap.
Used for "Similar Cards" feature in card browser.

Supports persistent caching for improved performance (2-6s → <500ms).

Uses "signature tags" approach: compares top 5 most frequent tags instead
of all tags, significantly improving performance and quality.
"""

import ast
import logging
import random
from pathlib import Path
from typing import Optional

import pandas as pd

from code.web.services.similarity_cache import SimilarityCache, get_cache

logger = logging.getLogger(__name__)


class CardSimilarity:
    """Calculate card similarity using theme tag overlap (Jaccard index) with caching."""

    def __init__(self, cards_df: Optional[pd.DataFrame] = None, cache: Optional[SimilarityCache] = None):
        """
        Initialize similarity calculator.

        Args:
            cards_df: DataFrame with card data. If None, loads from all_cards.parquet
            cache: SimilarityCache instance. If None, uses global singleton
        """
        if cards_df is None:
            # Load from default location
            parquet_path = Path(__file__).parents[3] / "card_files" / "all_cards.parquet"
            logger.info(f"Loading cards from {parquet_path}")
            self.cards_df = pd.read_parquet(parquet_path)
        else:
            self.cards_df = cards_df

        # Initialize cache
        self.cache = cache if cache is not None else get_cache()

        # Load theme frequencies from catalog
        self.theme_frequencies = self._load_theme_frequencies()

        # Pre-compute cleaned tags (with exclusions) for all cards (one-time cost, huge speedup)
        # This removes "Historics Matter" and "Legends Matter" from all cards
        self.cleaned_tags_cache = self._precompute_cleaned_tags()
        
        # Pre-compute card metadata (EDHREC rank) for fast lookups
        self._card_metadata = self._precompute_card_metadata()
        
        # Inverted index (tag -> set of card names) - built lazily on first use
        self._tag_to_cards_index = None

        logger.info(
            f"Initialized CardSimilarity with {len(self.cards_df)} cards "
            f"and {len(self.theme_frequencies)} theme frequencies "
            f"(cache: {'enabled' if self.cache.enabled else 'disabled'})"
        )

    def _load_theme_frequencies(self) -> dict[str, int]:
        """
        Load theme frequencies from theme_catalog.csv.

        Returns:
            Dict mapping theme name to card_count (higher = more common)
        """
        catalog_path = Path(__file__).parents[3] / "config" / "themes" / "theme_catalog.csv"

        try:
            # Read CSV, skipping comment line
            df = pd.read_csv(catalog_path, comment="#")

            # Create dict mapping theme -> card_count
            # Higher card_count = more common/frequent theme
            frequencies = dict(zip(df["theme"], df["card_count"]))

            logger.info(f"Loaded {len(frequencies)} theme frequencies from catalog")
            return frequencies

        except Exception as e:
            logger.warning(f"Failed to load theme frequencies: {e}, using empty dict")
            return {}

    def _precompute_cleaned_tags(self) -> dict[str, set[str]]:
        """
        Pre-compute cleaned tags for all cards.

        Removes overly common tags like "Historics Matter" and "Legends Matter"
        that don't provide meaningful similarity. This is done once during
        initialization to avoid recalculating for every comparison.

        Returns:
            Dict mapping card name -> cleaned tags (full set minus exclusions)
        """
        logger.info("Pre-computing cleaned tags for all cards...")
        excluded_tags = {"Historics Matter", "Legends Matter"}
        cleaned = {}

        for _, row in self.cards_df.iterrows():
            card_name = row["name"]
            tags = self.parse_theme_tags(row["themeTags"])

            if tags:
                # Remove excluded tags
                cleaned_tags = tags - excluded_tags
                if cleaned_tags:  # Only store if card has tags after exclusion
                    cleaned[card_name] = cleaned_tags

        logger.info(f"Pre-computed {len(cleaned)} card tag sets")
        return cleaned

    def _precompute_card_metadata(self) -> dict[str, dict]:
        """
        Pre-compute card metadata (EDHREC rank, etc.) for fast lookups.
        
        Returns:
            Dict mapping card name -> metadata dict
        """
        logger.info("Pre-computing card metadata...")
        metadata = {}
        
        for _, row in self.cards_df.iterrows():
            card_name = row["name"]
            edhrec_rank = row.get("edhrecRank")
            # Convert to float, use inf for NaN/None
            edhrec_rank = float(edhrec_rank) if pd.notna(edhrec_rank) else float('inf')
            
            metadata[card_name] = {
                "edhrecRank": edhrec_rank,
            }
        
        logger.info(f"Pre-computed metadata for {len(metadata)} cards")
        return metadata

    def _build_tag_index(self) -> None:
        """
        Build inverted index: tag -> set of card names that have this tag.
        
        This allows fast candidate filtering - instead of checking all 29k cards,
        we only check cards that share at least one tag with the target.
        
        Performance impact: Reduces 29k comparisons to typically 100-2000 comparisons.
        """
        logger.info("Building inverted tag index...")
        index = {}
        
        for card_name, tags in self.cleaned_tags_cache.items():
            for tag in tags:
                if tag not in index:
                    index[tag] = set()
                index[tag].add(card_name)
        
        self._tag_to_cards_index = index
        
        # Log statistics
        avg_cards_per_tag = sum(len(cards) for cards in index.values()) / len(index) if index else 0
        logger.info(
            f"Built tag index: {len(index)} unique tags, "
            f"avg {avg_cards_per_tag:.1f} cards per tag"
        )

    def get_signature_tags(
        self,
        card_tags: set[str],
        top_n: int = 5,
        random_n: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> set[str]:
        """
        Get signature tags for similarity comparison.

        Takes the most frequent (popular) tags PLUS random tags for diversity.
        This balances defining characteristics with discovery of niche synergies.

        Excludes overly common tags like "Historics Matter" and "Legends Matter"
        that appear on most legendary cards and don't provide meaningful similarity.

        Args:
            card_tags: Full set of card theme tags
            top_n: Number of most frequent tags to use (default 5)
            random_n: Number of random tags to add. If None, auto-scales:
                     - 6-10 tags: 1 random
                     - 11-15 tags: 2 random
                     - 16+ tags: 3 random
            seed: Random seed for reproducibility (default: None)

        Returns:
            Set of signature tags (top_n most frequent + random_n random)
        """
        # Exclude overly common tags that don't provide meaningful similarity
        excluded_tags = {"Historics Matter", "Legends Matter"}
        card_tags = card_tags - excluded_tags

        if len(card_tags) <= top_n:
            return card_tags  # Use all if card has few tags

        # Auto-scale random_n based on total tag count if not specified
        if random_n is None:
            tag_count = len(card_tags)
            if tag_count >= 16:
                random_n = 3
            elif tag_count >= 11:
                random_n = 2
            elif tag_count >= 6:
                random_n = 1
            else:
                random_n = 0  # Very few tags, no random needed

        # Sort tags by frequency (higher card_count = more common = higher priority)
        sorted_tags = sorted(
            card_tags,
            key=lambda t: -self.theme_frequencies.get(t, 0),  # Negate for descending order
        )

        # Take top N most frequent tags
        signature = set(sorted_tags[:top_n])

        # Add random tags from remaining tags
        remaining_tags = card_tags - signature
        if remaining_tags and random_n > 0:
            if seed is not None:
                random.seed(seed)
            
            # Sample min(random_n, len(remaining_tags)) to avoid errors
            sample_size = min(random_n, len(remaining_tags))
            random_tags = set(random.sample(list(remaining_tags), sample_size))
            
            signature = signature | random_tags

        return signature

    @staticmethod
    def parse_theme_tags(tags: str | list) -> set[str]:
        """
        Parse theme tags from string or list format.

        Args:
            tags: Theme tags as string representation of list or actual list

        Returns:
            Set of theme tag strings
        """
        # M4: Handle both scalar NA (CSV) and array values (Parquet)
        if pd.isna(tags) if isinstance(tags, (str, float, int, type(None))) else False:
            return set()
        
        if isinstance(tags, list):
            # M4: Parquet format - already a list
            return set(tags) if tags else set()

        if isinstance(tags, str):
            # Handle string representation of list: "['tag1', 'tag2']"
            try:
                parsed = ast.literal_eval(tags)
                if isinstance(parsed, list):
                    return set(parsed)
                return set()
            except (ValueError, SyntaxError):
                # If parsing fails, return empty set
                logger.warning(f"Failed to parse theme tags: {tags[:100]}")
                return set()

        return set()

    @staticmethod
    def calculate_similarity(tags_a: set[str], tags_b: set[str]) -> float:
        """
        Calculate Jaccard similarity between two sets of theme tags.

        Jaccard index = intersection / union

        Args:
            tags_a: First set of theme tags
            tags_b: Second set of theme tags

        Returns:
            Similarity score from 0.0 (no overlap) to 1.0 (identical)
        """
        if not tags_a or not tags_b:
            return 0.0

        intersection = len(tags_a & tags_b)
        union = len(tags_a | tags_b)

        if union == 0:
            return 0.0

        return intersection / union

    def get_card_tags(self, card_name: str) -> Optional[set[str]]:
        """
        Get theme tags for a specific card.

        Args:
            card_name: Name of the card

        Returns:
            Set of theme tags, or None if card not found
        """
        card_row = self.cards_df[self.cards_df["name"] == card_name]

        if card_row.empty:
            return None

        tags = card_row.iloc[0]["themeTags"]
        return self.parse_theme_tags(tags)

    def find_similar(
        self,
        card_name: str,
        threshold: float = 0.8,
        limit: int = 10,
        min_results: int = 3,
        adaptive: bool = True,
        use_cache: bool = True,
    ) -> list[dict]:
        """
        Find cards with similar theme tags.

        Uses adaptive threshold scaling to ensure minimum number of results.
        Tries 80% → 60% thresholds until min_results is met (skips 70% for performance).

        Checks cache first for pre-computed results, falls back to real-time calculation.

        Args:
            card_name: Name of the target card
            threshold: Starting similarity threshold (0.0-1.0), default 0.8 (80%)
            limit: Maximum number of results, default 10
            min_results: Minimum desired results for adaptive scaling, default 3
            adaptive: Enable adaptive threshold scaling, default True
            use_cache: Check cache first before calculating, default True

        Returns:
            List of dicts with keys: name, similarity, themeTags, edhrecRank, threshold_used
            Sorted by similarity descending, then by EDHREC rank ascending (more popular first)
            Returns empty list if card not found or has no tags
        """
        # Check cache first
        if use_cache and self.cache.enabled:
            cached_results = self.cache.get_similar(card_name, limit=limit, randomize=True)
            if cached_results is not None:
                logger.info(f"Cache HIT for '{card_name}' ({len(cached_results)} results, randomized)")
                return cached_results
            else:
                logger.info(f"Cache MISS for '{card_name}', calculating...")

        # Get target card tags
        target_tags = self.get_card_tags(card_name)

        if target_tags is None:
            logger.warning(f"Card not found: {card_name}")
            return []

        if not target_tags:
            logger.info(f"Card has no theme tags: {card_name}")
            return []

        # Get signature tags for TARGET card only (top 5 most frequent + 1-3 random)
        # This focuses the search on the target's defining characteristics
        # with some diversity from random tags
        
        # Use card name hash as seed for reproducible randomness per card
        card_seed = hash(card_name) % (2**31)
        target_signature = self.get_signature_tags(
            target_tags,
            top_n=5,
            seed=card_seed
        )

        logger.debug(
            f"Target '{card_name}': {len(target_tags)} tags → "
            f"{len(target_signature)} signature tags"
        )

        # Try adaptive thresholds if enabled
        thresholds_to_try = [threshold]
        if adaptive:
            # Build list of thresholds to try: 80% → 60% → 50% (skip 70% for performance)
            thresholds_to_try = []
            if threshold >= 0.8:
                thresholds_to_try.append(0.8)
            if threshold >= 0.6:
                thresholds_to_try.append(0.6)
            if threshold >= 0.5:
                thresholds_to_try.append(0.5)
            
            # Remove duplicates and sort descending
            thresholds_to_try = sorted(set(thresholds_to_try), reverse=True)

        results = []
        threshold_used = threshold

        for current_threshold in thresholds_to_try:
            # Use inverted index for fast candidate filtering
            # Instead of checking all 29k cards, only check cards that share at least one signature tag
            results = []
            
            # Build inverted index on first use (lazily)
            if self._tag_to_cards_index is None:
                self._build_tag_index()
            
            # Get candidate cards that share at least one signature tag
            # This drastically reduces the number of cards we need to check
            candidate_cards = set()
            for tag in target_signature:
                if tag in self._tag_to_cards_index:
                    candidate_cards.update(self._tag_to_cards_index[tag])
            
            # Remove the target card itself
            candidate_cards.discard(card_name)
            
            if not candidate_cards:
                continue  # No candidates at all, try lower threshold
            
            # Now calculate scores only for candidates (vectorized where possible)
            # Pre-filter candidates by checking if they meet minimum overlap requirement
            min_overlap = int(len(target_signature) * current_threshold)
            
            for candidate_name in candidate_cards:
                candidate_tags = self.cleaned_tags_cache.get(candidate_name)
                
                if not candidate_tags:
                    continue
                
                # Fast overlap check using set intersection
                overlap = target_signature & candidate_tags
                overlap_count = len(overlap)
                
                # Quick filter: skip if overlap too small
                if overlap_count < min_overlap:
                    continue
                
                # Calculate exact containment score
                containment_score = overlap_count / len(target_signature)
                
                if containment_score >= current_threshold:
                    # Get EDHREC rank efficiently from card metadata
                    edhrec_rank = self._card_metadata.get(candidate_name, {}).get('edhrecRank', float('inf'))
                    
                    results.append({
                        "name": candidate_name,
                        "similarity": containment_score,
                        "themeTags": list(candidate_tags),
                        "edhrecRank": edhrec_rank,
                    })

            # Sort by similarity descending, then by EDHREC rank ascending (lower is better)
            # Unranked cards (inf) will appear last
            results.sort(key=lambda x: (-x["similarity"], x["edhrecRank"]))

            # Check if we have enough results
            if len(results) >= min_results or not adaptive:
                threshold_used = current_threshold
                break
            
            # Log that we're trying a lower threshold
            logger.info(
                f"Found {len(results)} results at {current_threshold:.0%} "
                f"for '{card_name}', trying lower threshold..."
            )

        # Add threshold_used to results
        for result in results:
            result["threshold_used"] = threshold_used

        logger.info(
            f"Found {len(results)} similar cards for '{card_name}' "
            f"at {threshold_used:.0%} threshold"
        )

        final_results = results[:limit]

        # Cache the results for future lookups
        if use_cache and self.cache.enabled and final_results:
            self.cache.set_similar(card_name, final_results)
            logger.debug(f"Cached {len(final_results)} results for '{card_name}'")

        return final_results
