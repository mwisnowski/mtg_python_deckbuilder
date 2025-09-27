Frozen test dataset for deterministic tests.

Use by setting environment variable CSV_FILES_DIR=csv_files/testdata (or absolute path in Docker).

Expected minimal files:
- cards.csv (flattened all-cards dataset for validation endpoints)
- commander_cards.csv
- *_cards.csv per color identity needed by tests (e.g., colorless_cards.csv)

Keep this tiny and representative; avoid adding large data.
