"""
Full audit of Protection-tagged cards with kindred metadata support (M2 Phase 2).

Created: October 8, 2025
Purpose: Audit and validate Protection tag precision after implementing grant detection.
         Can be re-run periodically to check tagging quality.

This script audits ALL Protection-tagged cards and categorizes them:
- Grant: Gives broad protection to other permanents YOU control
- Kindred: Gives protection to specific creature types (metadata tags)
- Mixed: Both broad and kindred/inherent
- Inherent: Only has protection itself
- ConditionalSelf: Only conditionally grants to itself
- Opponent: Grants to opponent's permanents
- Neither: False positive

Outputs:
- m2_audit_v2.json: Full analysis with summary
- m2_audit_v2_grant.csv: Cards for main Protection tag
- m2_audit_v2_kindred.csv: Cards for kindred metadata tags
- m2_audit_v2_mixed.csv: Cards with both broad and kindred grants
- m2_audit_v2_conditional.csv: Conditional self-grants (exclude)
- m2_audit_v2_inherent.csv: Inherent protection only (exclude)
- m2_audit_v2_opponent.csv: Opponent grants (exclude)
- m2_audit_v2_neither.csv: False positives (exclude)
- m2_audit_v2_all.csv: All cards combined
"""

import sys
from pathlib import Path
import pandas as pd
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from code.tagging.protection_grant_detection import (
    categorize_protection_card,
    get_kindred_protection_tags,
    is_granting_protection,
)

def load_all_cards():
    """Load all cards from color/identity CSV files."""
    csv_dir = project_root / 'csv_files'
    
    # Get all color/identity CSVs (not the raw cards.csv)
    csv_files = list(csv_dir.glob('*_cards.csv'))
    csv_files = [f for f in csv_files if f.stem not in ['cards', 'testdata']]
    
    all_cards = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            all_cards.append(df)
        except Exception as e:
            print(f"Warning: Could not load {csv_file.name}: {e}")
    
    # Combine all DataFrames
    combined = pd.concat(all_cards, ignore_index=True)
    
    # Drop duplicates (cards appear in multiple color files)
    combined = combined.drop_duplicates(subset=['name'], keep='first')
    
    return combined

def audit_all_protection_cards():
    """Audit all Protection-tagged cards."""
    print("Loading all cards...")
    df = load_all_cards()
    
    print(f"Total cards loaded: {len(df)}")
    
    # Filter to Protection-tagged cards (column is 'themeTags' in color CSVs)
    df_prot = df[df['themeTags'].str.contains('Protection', case=False, na=False)].copy()
    
    print(f"Protection-tagged cards: {len(df_prot)}")
    
    # Categorize each card
    categories = []
    grants_list = []
    kindred_tags_list = []
    
    for idx, row in df_prot.iterrows():
        name = row['name']
        text = str(row.get('text', '')).replace('\\n', '\n')  # Convert escaped newlines to real newlines
        keywords = str(row.get('keywords', ''))
        card_type = str(row.get('type', ''))
        
        # Categorize with kindred exclusion enabled
        category = categorize_protection_card(name, text, keywords, card_type, exclude_kindred=True)
        
        # Check if it grants broadly
        grants_broad = is_granting_protection(text, keywords, exclude_kindred=True)
        
        # Get kindred tags
        kindred_tags = get_kindred_protection_tags(text)
        
        categories.append(category)
        grants_list.append(grants_broad)
        kindred_tags_list.append(', '.join(sorted(kindred_tags)) if kindred_tags else '')
    
    df_prot['category'] = categories
    df_prot['grants_broad'] = grants_list
    df_prot['kindred_tags'] = kindred_tags_list
    
    # Generate summary (convert numpy types to native Python for JSON serialization)
    summary = {
        'total': int(len(df_prot)),
        'categories': {k: int(v) for k, v in df_prot['category'].value_counts().to_dict().items()},
        'grants_broad_count': int(df_prot['grants_broad'].sum()),
        'kindred_cards_count': int((df_prot['kindred_tags'] != '').sum()),
    }
    
    # Calculate keep vs remove
    keep_categories = {'Grant', 'Mixed'}
    kindred_only = df_prot[df_prot['category'] == 'Kindred']
    keep_count = len(df_prot[df_prot['category'].isin(keep_categories)])
    remove_count = len(df_prot[~df_prot['category'].isin(keep_categories | {'Kindred'})])
    
    summary['keep_main_tag'] = keep_count
    summary['kindred_metadata'] = len(kindred_only)
    summary['remove'] = remove_count
    summary['precision_estimate'] = round((keep_count / len(df_prot)) * 100, 1) if len(df_prot) > 0 else 0
    
    # Print summary
    print(f"\n{'='*60}")
    print("AUDIT SUMMARY")
    print(f"{'='*60}")
    print(f"Total Protection-tagged cards: {summary['total']}")
    print(f"\nCategories:")
    for cat, count in sorted(summary['categories'].items()):
        pct = (count / summary['total']) * 100
        print(f"  {cat:20s} {count:4d} ({pct:5.1f}%)")
    
    print(f"\n{'='*60}")
    print(f"Main Protection tag:  {keep_count:4d} ({keep_count/len(df_prot)*100:5.1f}%)")
    print(f"Kindred metadata only: {len(kindred_only):4d} ({len(kindred_only)/len(df_prot)*100:5.1f}%)")
    print(f"Remove:               {remove_count:4d} ({remove_count/len(df_prot)*100:5.1f}%)")
    print(f"{'='*60}")
    print(f"Precision estimate:   {summary['precision_estimate']}%")
    print(f"{'='*60}\n")
    
    # Export results
    output_dir = project_root / 'logs' / 'roadmaps' / 'source' / 'tagging_refinement'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Export JSON summary
    with open(output_dir / 'm2_audit_v2.json', 'w') as f:
        json.dump({
            'summary': summary,
            'cards': df_prot[['name', 'type', 'category', 'grants_broad', 'kindred_tags', 'keywords', 'text']].to_dict(orient='records')
        }, f, indent=2)
    
    # Export CSVs by category
    export_cols = ['name', 'type', 'category', 'grants_broad', 'kindred_tags', 'keywords', 'text']
    
    # Grant category
    df_grant = df_prot[df_prot['category'] == 'Grant']
    df_grant[export_cols].to_csv(output_dir / 'm2_audit_v2_grant.csv', index=False)
    print(f"Exported {len(df_grant)} Grant cards to m2_audit_v2_grant.csv")
    
    # Kindred category
    df_kindred = df_prot[df_prot['category'] == 'Kindred']
    df_kindred[export_cols].to_csv(output_dir / 'm2_audit_v2_kindred.csv', index=False)
    print(f"Exported {len(df_kindred)} Kindred cards to m2_audit_v2_kindred.csv")
    
    # Mixed category
    df_mixed = df_prot[df_prot['category'] == 'Mixed']
    df_mixed[export_cols].to_csv(output_dir / 'm2_audit_v2_mixed.csv', index=False)
    print(f"Exported {len(df_mixed)} Mixed cards to m2_audit_v2_mixed.csv")
    
    # ConditionalSelf category
    df_conditional = df_prot[df_prot['category'] == 'ConditionalSelf']
    df_conditional[export_cols].to_csv(output_dir / 'm2_audit_v2_conditional.csv', index=False)
    print(f"Exported {len(df_conditional)} ConditionalSelf cards to m2_audit_v2_conditional.csv")
    
    # Inherent category
    df_inherent = df_prot[df_prot['category'] == 'Inherent']
    df_inherent[export_cols].to_csv(output_dir / 'm2_audit_v2_inherent.csv', index=False)
    print(f"Exported {len(df_inherent)} Inherent cards to m2_audit_v2_inherent.csv")
    
    # Opponent category
    df_opponent = df_prot[df_prot['category'] == 'Opponent']
    df_opponent[export_cols].to_csv(output_dir / 'm2_audit_v2_opponent.csv', index=False)
    print(f"Exported {len(df_opponent)} Opponent cards to m2_audit_v2_opponent.csv")
    
    # Neither category
    df_neither = df_prot[df_prot['category'] == 'Neither']
    df_neither[export_cols].to_csv(output_dir / 'm2_audit_v2_neither.csv', index=False)
    print(f"Exported {len(df_neither)} Neither cards to m2_audit_v2_neither.csv")
    
    # All cards
    df_prot[export_cols].to_csv(output_dir / 'm2_audit_v2_all.csv', index=False)
    print(f"Exported {len(df_prot)} total cards to m2_audit_v2_all.csv")
    
    print(f"\nAll files saved to: {output_dir}")
    
    return df_prot, summary

if __name__ == '__main__':
    df_results, summary = audit_all_protection_cards()
