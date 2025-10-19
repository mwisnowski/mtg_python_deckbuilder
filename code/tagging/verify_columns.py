"""Quick verification script to check column preservation after tagging."""

import pandas as pd
from code.path_util import get_processed_cards_path

def verify_columns():
    """Verify that all expected columns are present after tagging."""
    path = get_processed_cards_path()
    df = pd.read_parquet(path)
    
    print(f"Loaded {len(df):,} cards from {path}")
    print(f"\nColumns ({len(df.columns)}):")
    for col in df.columns:
        print(f"  - {col}")
    
    # Check critical columns
    expected = ['isCommander', 'isBackground', 'metadataTags', 'themeTags']
    missing = [col for col in expected if col not in df.columns]
    
    if missing:
        print(f"\n❌ MISSING COLUMNS: {missing}")
        return False
    
    print(f"\n✅ All critical columns present!")
    
    # Check counts
    if 'isCommander' in df.columns:
        print(f"   isCommander: {df['isCommander'].sum()} True")
    if 'isBackground' in df.columns:
        print(f"   isBackground: {df['isBackground'].sum()} True")
    if 'themeTags' in df.columns:
        total_tags = df['themeTags'].apply(lambda x: len(x) if isinstance(x, list) else 0).sum()
        print(f"   themeTags: {total_tags:,} total tags")
    if 'metadataTags' in df.columns:
        total_meta = df['metadataTags'].apply(lambda x: len(x) if isinstance(x, list) else 0).sum()
        print(f"   metadataTags: {total_meta:,} total tags")
    
    return True

if __name__ == "__main__":
    verify_columns()
