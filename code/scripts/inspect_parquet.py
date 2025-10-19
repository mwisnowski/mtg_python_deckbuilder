"""Inspect MTGJSON Parquet file schema and compare to CSV."""

import pandas as pd
import os
import sys

def inspect_parquet():
    """Load and inspect Parquet file."""
    parquet_path = 'csv_files/cards_parquet_test.parquet'
    
    if not os.path.exists(parquet_path):
        print(f"Error: {parquet_path} not found")
        return
    
    print("Loading Parquet file...")
    df = pd.read_parquet(parquet_path)
    
    print("\n=== PARQUET FILE INFO ===")
    print(f"Rows: {len(df):,}")
    print(f"Columns: {len(df.columns)}")
    print(f"File size: {os.path.getsize(parquet_path) / 1024 / 1024:.2f} MB")
    
    print("\n=== PARQUET COLUMNS AND TYPES ===")
    for col in sorted(df.columns):
        dtype = str(df[col].dtype)
        non_null = df[col].notna().sum()
        null_pct = (1 - non_null / len(df)) * 100
        print(f"  {col:30s} {dtype:15s} ({null_pct:5.1f}% null)")
    
    print("\n=== SAMPLE DATA (first card) ===")
    first_card = df.iloc[0].to_dict()
    for key, value in sorted(first_card.items()):
        if isinstance(value, (list, dict)):
            print(f"  {key}: {type(value).__name__} with {len(value)} items")
        else:
            value_str = str(value)[:80]
            print(f"  {key}: {value_str}")
    
    return df

def compare_to_csv():
    """Compare Parquet columns to CSV columns."""
    csv_path = 'csv_files/cards.csv'
    parquet_path = 'csv_files/cards_parquet_test.parquet'
    
    if not os.path.exists(csv_path):
        print(f"\nNote: {csv_path} not found, skipping comparison")
        return
    
    print("\n\n=== CSV FILE INFO ===")
    print("Loading CSV file...")
    df_csv = pd.read_csv(csv_path, low_memory=False, nrows=1)
    
    csv_size = os.path.getsize(csv_path) / 1024 / 1024
    print(f"File size: {csv_size:.2f} MB")
    print(f"Columns: {len(df_csv.columns)}")
    
    print("\n=== CSV COLUMNS ===")
    csv_cols = set(df_csv.columns)
    for col in sorted(df_csv.columns):
        print(f"  {col}")
    
    # Load parquet columns
    df_parquet = pd.read_parquet(parquet_path)
    parquet_cols = set(df_parquet.columns)
    
    print("\n\n=== SCHEMA COMPARISON ===")
    
    # Columns in both
    common = csv_cols & parquet_cols
    print(f"\n✓ Columns in both (n={len(common)}):")
    for col in sorted(common):
        csv_type = str(df_csv[col].dtype)
        parquet_type = str(df_parquet[col].dtype)
        if csv_type != parquet_type:
            print(f"  {col:30s} CSV: {csv_type:15s} Parquet: {parquet_type}")
        else:
            print(f"  {col:30s} {csv_type}")
    
    # CSV only
    csv_only = csv_cols - parquet_cols
    if csv_only:
        print(f"\n⚠ Columns only in CSV (n={len(csv_only)}):")
        for col in sorted(csv_only):
            print(f"  {col}")
    
    # Parquet only
    parquet_only = parquet_cols - csv_cols
    if parquet_only:
        print(f"\n✓ Columns only in Parquet (n={len(parquet_only)}):")
        for col in sorted(parquet_only):
            print(f"  {col}")
    
    # File size comparison
    parquet_size = os.path.getsize(parquet_path) / 1024 / 1024
    size_reduction = (1 - parquet_size / csv_size) * 100
    print(f"\n=== FILE SIZE COMPARISON ===")
    print(f"CSV:     {csv_size:.2f} MB")
    print(f"Parquet: {parquet_size:.2f} MB")
    print(f"Savings: {size_reduction:.1f}%")

if __name__ == "__main__":
    df = inspect_parquet()
    compare_to_csv()
