"""
Tests for AllCardsLoader and CardQueryBuilder

Tests cover:
- Loading and caching behavior
- Single and batch card lookups
- Color, theme, and type filtering
- Text search
- Query builder fluent API
- Performance benchmarks
"""

from __future__ import annotations

import os
import tempfile
import time

import pandas as pd
import pytest

from code.services.all_cards_loader import AllCardsLoader
from code.services.card_query_builder import CardQueryBuilder


@pytest.fixture
def sample_cards_df():
    """Create a sample DataFrame for testing."""
    return pd.DataFrame(
        {
            "name": [
                "Sol Ring",
                "Lightning Bolt",
                "Counterspell",
                "Giant Growth",
                "Goblin Token Maker",
                "Dark Ritual",
                "Swords to Plowshares",
                "Birds of Paradise",
            ],
            "colorIdentity": ["Colorless", "R", "U", "G", "R", "B", "W", "G"],
            "type": [
                "Artifact",
                "Instant",
                "Instant",
                "Instant",
                "Creature — Goblin",
                "Instant",
                "Instant",
                "Creature — Bird",
            ],
            "text": [
                "Add two mana",
                "Deal 3 damage",
                "Counter target spell",
                "Target creature gets +3/+3",
                "When this enters, create two 1/1 red Goblin creature tokens",
                "Add three black mana",
                "Exile target creature",
                "Flying, Add one mana of any color",
            ],
            "themeTags": [
                "",
                "burn,damage",
                "control,counterspells",
                "combat,pump",
                "tokens,goblins",
                "ritual,fast-mana",
                "removal,exile",
                "ramp,mana-dork",
            ],
        }
    )


@pytest.fixture
def sample_parquet_file(sample_cards_df):
    """Create a temporary Parquet file for testing."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".parquet") as tmp:
        sample_cards_df.to_parquet(tmp.name, engine="pyarrow")
        yield tmp.name
    os.unlink(tmp.name)


def test_loader_initialization(sample_parquet_file):
    """Test AllCardsLoader initialization."""
    loader = AllCardsLoader(file_path=sample_parquet_file, cache_ttl=60)
    assert loader.file_path == sample_parquet_file
    assert loader.cache_ttl == 60
    assert loader._df is None


def test_loader_load(sample_parquet_file):
    """Test loading Parquet file."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    df = loader.load()
    assert len(df) == 8
    assert "name" in df.columns
    assert "colorIdentity" in df.columns


def test_loader_caching(sample_parquet_file):
    """Test that caching works and doesn't reload unnecessarily."""
    loader = AllCardsLoader(file_path=sample_parquet_file, cache_ttl=300)

    # First load
    start_time = time.time()
    df1 = loader.load()
    first_load_time = time.time() - start_time

    # Second load (should use cache)
    start_time = time.time()
    df2 = loader.load()
    cached_load_time = time.time() - start_time

    # Cache should be much faster
    assert cached_load_time < first_load_time / 2
    assert df1 is df2  # Same object


def test_loader_force_reload(sample_parquet_file):
    """Test force_reload flag."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    df1 = loader.load()
    df2 = loader.load(force_reload=True)

    assert df1 is not df2  # Different objects
    assert len(df1) == len(df2)  # Same data


def test_loader_cache_expiration(sample_parquet_file):
    """Test cache expiration after TTL."""
    loader = AllCardsLoader(file_path=sample_parquet_file, cache_ttl=1)

    df1 = loader.load()
    time.sleep(1.1)  # Wait for TTL to expire
    df2 = loader.load()

    assert df1 is not df2  # Should have reloaded


def test_get_by_name(sample_parquet_file):
    """Test single card lookup by name."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    card = loader.get_by_name("Sol Ring")
    assert card is not None
    assert card["name"] == "Sol Ring"
    assert card["colorIdentity"] == "Colorless"

    # Non-existent card
    card = loader.get_by_name("Nonexistent Card")
    assert card is None


def test_get_by_names(sample_parquet_file):
    """Test batch card lookup by names."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    cards = loader.get_by_names(["Sol Ring", "Lightning Bolt", "Counterspell"])
    assert len(cards) == 3
    assert "Sol Ring" in cards["name"].values
    assert "Lightning Bolt" in cards["name"].values

    # Empty list
    cards = loader.get_by_names([])
    assert len(cards) == 0

    # Non-existent cards
    cards = loader.get_by_names(["Nonexistent1", "Nonexistent2"])
    assert len(cards) == 0


def test_filter_by_color_identity(sample_parquet_file):
    """Test color identity filtering."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    # Single color
    red_cards = loader.filter_by_color_identity(["R"])
    assert len(red_cards) == 2
    assert "Lightning Bolt" in red_cards["name"].values
    assert "Goblin Token Maker" in red_cards["name"].values

    # Colorless
    colorless = loader.filter_by_color_identity(["Colorless"])
    assert len(colorless) == 1
    assert colorless["name"].values[0] == "Sol Ring"


def test_filter_by_themes(sample_parquet_file):
    """Test theme filtering."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    # Single theme
    token_cards = loader.filter_by_themes(["tokens"], mode="any")
    assert len(token_cards) == 1
    assert token_cards["name"].values[0] == "Goblin Token Maker"

    # Multiple themes (any)
    cards = loader.filter_by_themes(["burn", "removal"], mode="any")
    assert len(cards) == 2  # Lightning Bolt and Swords to Plowshares

    # Multiple themes (all)
    cards = loader.filter_by_themes(["tokens", "goblins"], mode="all")
    assert len(cards) == 1
    assert cards["name"].values[0] == "Goblin Token Maker"


def test_filter_by_type(sample_parquet_file):
    """Test type filtering."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    creatures = loader.filter_by_type("Creature")
    assert len(creatures) == 2
    assert "Goblin Token Maker" in creatures["name"].values
    assert "Birds of Paradise" in creatures["name"].values

    instants = loader.filter_by_type("Instant")
    assert len(instants) == 5


def test_search(sample_parquet_file):
    """Test text search."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    # Search in text
    results = loader.search("token")
    assert len(results) >= 1
    assert "Goblin Token Maker" in results["name"].values

    # Search in name
    results = loader.search("Sol")
    assert len(results) == 1
    assert results["name"].values[0] == "Sol Ring"

    # Limit results
    results = loader.search("mana", limit=1)
    assert len(results) == 1


def test_get_stats(sample_parquet_file):
    """Test stats retrieval."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    loader.load()

    stats = loader.get_stats()
    assert stats["total_cards"] == 8
    assert stats["cached"] is True
    assert stats["file_size_mb"] >= 0  # Small test file may round to 0
    assert "cache_age_seconds" in stats


def test_clear_cache(sample_parquet_file):
    """Test cache clearing."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    loader.load()

    assert loader._df is not None
    loader.clear_cache()
    assert loader._df is None


def test_query_builder_basic(sample_parquet_file):
    """Test basic query builder usage."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    builder = CardQueryBuilder(loader=loader)

    # Execute without filters
    results = builder.execute()
    assert len(results) == 8

    # Single filter
    results = builder.reset().colors(["R"]).execute()
    assert len(results) == 2


def test_query_builder_chaining(sample_parquet_file):
    """Test query builder method chaining."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    results = (
        CardQueryBuilder(loader=loader)
        .types("Creature")
        .themes(["tokens"], mode="any")
        .execute()
    )
    assert len(results) == 1
    assert results["name"].values[0] == "Goblin Token Maker"


def test_query_builder_names(sample_parquet_file):
    """Test query builder with specific names."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    results = (
        CardQueryBuilder(loader=loader)
        .names(["Sol Ring", "Lightning Bolt"])
        .execute()
    )
    assert len(results) == 2


def test_query_builder_limit(sample_parquet_file):
    """Test query builder limit."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    results = CardQueryBuilder(loader=loader).limit(3).execute()
    assert len(results) == 3


def test_query_builder_count(sample_parquet_file):
    """Test query builder count method."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    count = CardQueryBuilder(loader=loader).types("Instant").count()
    assert count == 5


def test_query_builder_first(sample_parquet_file):
    """Test query builder first method."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    card = CardQueryBuilder(loader=loader).colors(["R"]).first()
    assert card is not None
    assert card["colorIdentity"] == "R"

    # No results
    card = CardQueryBuilder(loader=loader).colors(["X"]).first()
    assert card is None


def test_query_builder_complex(sample_parquet_file):
    """Test complex query with multiple filters."""
    loader = AllCardsLoader(file_path=sample_parquet_file)

    results = (
        CardQueryBuilder(loader=loader)
        .types("Instant")
        .colors(["R"])
        .search("damage")
        .limit(5)
        .execute()
    )
    assert len(results) == 1
    assert results["name"].values[0] == "Lightning Bolt"


def test_performance_single_lookup(sample_parquet_file):
    """Benchmark single card lookup performance."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    loader.load()  # Warm up cache

    start = time.time()
    for _ in range(100):
        loader.get_by_name("Sol Ring")
    elapsed = time.time() - start

    avg_time_ms = (elapsed / 100) * 1000
    print(f"\nSingle lookup avg: {avg_time_ms:.3f}ms")
    assert avg_time_ms < 10  # Should be <10ms per lookup


def test_performance_batch_lookup(sample_parquet_file):
    """Benchmark batch card lookup performance."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    loader.load()  # Warm up cache

    names = ["Sol Ring", "Lightning Bolt", "Counterspell"]

    start = time.time()
    for _ in range(100):
        loader.get_by_names(names)
    elapsed = time.time() - start

    avg_time_ms = (elapsed / 100) * 1000
    print(f"\nBatch lookup (3 cards) avg: {avg_time_ms:.3f}ms")
    assert avg_time_ms < 15  # Should be <15ms per batch


def test_performance_filter_by_color(sample_parquet_file):
    """Benchmark color filtering performance."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    loader.load()  # Warm up cache

    start = time.time()
    for _ in range(100):
        loader.filter_by_color_identity(["R"])
    elapsed = time.time() - start

    avg_time_ms = (elapsed / 100) * 1000
    print(f"\nColor filter avg: {avg_time_ms:.3f}ms")
    assert avg_time_ms < 20  # Should be <20ms per filter


def test_performance_search(sample_parquet_file):
    """Benchmark text search performance."""
    loader = AllCardsLoader(file_path=sample_parquet_file)
    loader.load()  # Warm up cache

    start = time.time()
    for _ in range(100):
        loader.search("token", limit=100)
    elapsed = time.time() - start

    avg_time_ms = (elapsed / 100) * 1000
    print(f"\nText search avg: {avg_time_ms:.3f}ms")
    assert avg_time_ms < 50  # Should be <50ms per search
