# All Cards Consolidation - Migration Guide

## Overview
This guide covers the migration from individual card CSV files to the consolidated `all_cards.parquet` format introduced in v2.8.0. The new format provides:

- **87% smaller file size** (3.74 MB vs ~30 MB for CSVs)
- **2-5x faster queries** (single lookup ~1.3ms, filters <70ms)
- **Improved caching** with automatic reload on file changes
- **Unified query API** via `AllCardsLoader` and `CardQueryBuilder`

## Migration Timeline

### Phase 1: v2.8.0 (Current) - Soft Launch
- ✅ AllCardsLoader and CardQueryBuilder available
- ✅ Automatic aggregation after tagging
- ✅ Legacy adapter functions provided for backward compatibility
- ✅ Feature flag `USE_ALL_CARDS_FILE=1` (enabled by default)
- ✅ Deprecation warnings logged when using legacy functions
- **cards.csv still supported** (kept for compatibility)
- **commander_cards.csv replaced** by `commander_cards.parquet`

### Phase 2: v2.9.0 - Broader Adoption
- Update deck_builder modules to use AllCardsLoader directly
- Update web routes to use new query API
- Continue supporting legacy adapter for external code
- Increase test coverage for real-world usage patterns

### Phase 3: v3.0.0 - Primary Method
- New code must use AllCardsLoader (no new legacy adapter usage)
- Legacy adapter still works but discouraged
- Documentation emphasizes new API
- cards.csv continues to work (not deprecated yet)

### Phase 4: v3.1.0+ - Sunset Legacy (Future)
- Remove legacy adapter functions
- Remove individual card CSV file support (cards.csv sunset)
- **commander_cards.parquet permanently replaces CSV version**
- All code uses AllCardsLoader exclusively

## Quick Start

### For New Code (Recommended)

```python
from code.services.all_cards_loader import AllCardsLoader
from code.services.card_query_builder import CardQueryBuilder

# Simple loading
loader = AllCardsLoader()
all_cards = loader.load()

# Single card lookup
sol_ring = loader.get_by_name("Sol Ring")

# Batch lookup
cards = loader.get_by_names(["Sol Ring", "Lightning Bolt", "Counterspell"])

# Filtering
red_cards = loader.filter_by_color_identity(["R"])
token_cards = loader.filter_by_themes(["tokens"], mode="any")
creatures = loader.filter_by_type("Creature")

# Text search
results = loader.search("create token", limit=100)

# Complex queries with fluent API
results = (CardQueryBuilder()
    .colors(["G"])
    .themes(["ramp"], mode="any")
    .types("Creature")
    .limit(20)
    .execute())
```

### For Existing Code (Legacy Adapter)

If you have existing code using old file-loading patterns, the legacy adapter provides backward compatibility:

```python
# Old code continues to work (with deprecation warnings)
from code.services.legacy_loader_adapter import (
    load_all_cards,
    load_cards_by_name,
    load_cards_by_type,
    load_cards_with_tag,
)

# These still work but log deprecation warnings
all_cards = load_all_cards()
sol_ring = load_cards_by_name("Sol Ring")
creatures = load_cards_by_type("Creature")
token_cards = load_cards_with_tag("tokens")
```

**Important**: Migrate to the new API as soon as possible. Legacy functions will be removed in v3.1+.

## Migration Steps

### Step 1: Update Imports

**Before:**
```python
# Old pattern (if you were loading cards directly)
import pandas as pd
df = pd.read_csv("csv_files/some_card.csv")
```

**After:**
```python
from code.services.all_cards_loader import AllCardsLoader

loader = AllCardsLoader()
card = loader.get_by_name("Card Name")
```

### Step 2: Update Query Patterns

**Before:**
```python
# Old: Manual filtering
all_cards = load_all_individual_csvs()  # Slow
creatures = all_cards[all_cards["type"].str.contains("Creature")]
red_creatures = creatures[creatures["colorIdentity"] == "R"]
```

**After:**
```python
# New: Efficient queries
loader = AllCardsLoader()
red_creatures = (CardQueryBuilder(loader)
    .colors(["R"])
    .types("Creature")
    .execute())
```

### Step 3: Update Caching

**Before:**
```python
# Old: Manual caching
_cache = {}
def get_card(name):
    if name not in _cache:
        _cache[name] = load_from_csv(name)
    return _cache[name]
```

**After:**
```python
# New: Built-in caching
loader = AllCardsLoader()  # Caches automatically
card = loader.get_by_name(name)  # Fast on repeat calls
```

## Feature Flag

The `USE_ALL_CARDS_FILE` environment variable controls whether the consolidated Parquet file is used:

```bash
# Enable (default)
USE_ALL_CARDS_FILE=1

# Disable (fallback to old method)
USE_ALL_CARDS_FILE=0
```

**When to disable:**
- Troubleshooting issues with the new loader
- Testing backward compatibility
- Temporary fallback during migration

## Performance Comparison

| Operation | Old (CSV) | New (Parquet) | Improvement |
|-----------|-----------|---------------|-------------|
| Initial load | ~2-3s | 0.104s | 20-30x faster |
| Single lookup | ~50-100ms | 1.3ms | 40-75x faster |
| Color filter | ~200ms | 2.1ms | 95x faster |
| Theme filter | ~500ms | 67ms | 7.5x faster |
| File size | ~30 MB | 3.74 MB | 87% smaller |

## Troubleshooting

### "all_cards.parquet not found"

Run the aggregation process:
1. Web UI: Go to Setup page → "Rebuild Card Files" button
2. CLI: `python code/scripts/aggregate_cards.py`
3. Automatic: Run tagging workflow (aggregation happens automatically)

### Deprecation Warnings

```
DEPRECATION: load_cards_by_name() called. Migrate to AllCardsLoader().get_by_name() before v3.1+
```

**Solution**: Update your code to use the new API as shown in this guide.

### Performance Issues

```python
# Check cache status
loader = AllCardsLoader()
stats = loader.get_stats()
print(stats)  # Shows cache age, file size, etc.

# Force reload if data seems stale
loader.load(force_reload=True)

# Clear cache
loader.clear_cache()
```

### Feature Flag Not Working

Ensure environment variable is set before importing:
```python
import os
os.environ['USE_ALL_CARDS_FILE'] = '1'

# Then import
from code.services.all_cards_loader import AllCardsLoader
```

## Testing Your Migration

```python
# Run migration compatibility tests
pytest code/tests/test_migration_compatibility.py -v

# Run all cards loader tests
pytest code/tests/test_all_cards_loader.py -v
```

## FAQ

**Q: Do I need to regenerate all_cards.parquet after tagging?**
A: No, it's automatic. Aggregation runs after tagging completes. You can manually trigger via "Rebuild Card Files" button if needed.

**Q: What happens to cards.csv?**
A: Still supported through v3.0.x for compatibility. Will be sunset in v3.1+. Start migrating now.

**Q: What about commander_cards.csv?**
A: Already replaced by `commander_cards.parquet` in v2.8.0. CSV version is no longer used.

**Q: Can I use both methods during migration?**
A: Yes, the legacy adapter allows mixed usage, but aim to fully migrate to the new API.

**Q: Will my existing decks break?**
A: No, existing decks are unaffected. This only changes how cards are loaded internally.

**Q: How do I disable the new loader?**
A: Set `USE_ALL_CARDS_FILE=0` environment variable. Not recommended except for troubleshooting.

**Q: Are there any breaking changes?**
A: No breaking changes in v2.8.0. Legacy functions work with deprecation warnings. Breaking changes planned for v3.1+.

## Support

If you encounter issues during migration:
1. Check deprecation warnings in logs
2. Run migration compatibility tests
3. Try disabling feature flag temporarily
4. File an issue on GitHub with details

## Summary

✅ **Use AllCardsLoader** for all new code
✅ **Migrate existing code** using this guide
✅ **Test thoroughly** with provided test suites
✅ **Monitor deprecation warnings** and address them
✅ **Plan ahead** for v3.1+ sunset of legacy functions

The new consolidated format provides significant performance improvements and a cleaner API. Start migrating today!
