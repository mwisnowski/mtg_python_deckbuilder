#!/bin/bash
# Quick test script for Docker volume mounting

echo "=== MTG Deckbuilder Docker Test ==="
echo "Current directory: $(pwd)"
echo "User: $(whoami)"
echo ""

# Create test directories
echo "Creating test directories..."
mkdir -p test_deck_files test_logs test_csv_files

# Test Docker volume mounting
echo "Testing Docker volume mounting..."
docker run --rm \
    -v "$(pwd)/test_deck_files:/app/deck_files" \
    -v "$(pwd)/test_logs:/app/logs" \
    -v "$(pwd)/test_csv_files:/app/csv_files" \
    python:3.11-slim /bin/bash -c "
        echo 'Inside container:'
        echo 'Working dir: \$(pwd)'
        echo 'Creating test files...'
        echo 'test content' > /app/deck_files/test.txt
        echo 'log content' > /app/logs/test.log
        echo 'csv content' > /app/csv_files/test.csv
        echo 'Files created successfully'
        ls -la /app/deck_files/ /app/logs/ /app/csv_files/
    "

echo ""
echo "Checking files on host system..."
echo "Deck files:"
ls -la test_deck_files/
echo "Log files:"
ls -la test_logs/
echo "CSV files:"
ls -la test_csv_files/

# Cleanup
echo ""
echo "Cleaning up test files..."
rm -rf test_deck_files test_logs test_csv_files

echo "Test complete!"
