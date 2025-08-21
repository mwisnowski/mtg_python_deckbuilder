#!/bin/bash
# Diagnostic script to debug Docker volume mounting issues

echo "=== MTG Deckbuilder Volume Mount Diagnostics ==="
echo "Date: $(date)"
echo "User: $(whoami)"
echo "Working Directory: $(pwd)"
echo ""

# Check if Docker is working
echo "=== Docker Info ==="
docker --version
echo ""

# Check host directories
echo "=== Host Directory Check ==="
echo "Current directory contents:"
ls -la

echo ""
echo "Checking for data directories:"
for dir in deck_files logs csv_files; do
    if [ -d "$dir" ]; then
        echo "✓ $dir exists"
        echo "  Permissions: $(ls -ld $dir | awk '{print $1, $3, $4}')"
        echo "  Contents: $(ls -la $dir | wc -l) items"
        if [ "$(ls -A $dir)" ]; then
            echo "  Files: $(ls -A $dir | head -3)"
        else
            echo "  (empty)"
        fi
    else
        echo "✗ $dir missing"
        echo "  Creating..."
        mkdir -p "$dir"
        chmod 755 "$dir"
    fi
    echo ""
done

# Test basic Docker volume mounting
echo "=== Docker Volume Mount Test ==="
echo "Testing if Docker can write to host directories..."

docker run --rm \
    -v "$(pwd)/deck_files:/test/deck_files" \
    -v "$(pwd)/logs:/test/logs" \
    -v "$(pwd)/csv_files:/test/csv_files" \
    alpine:latest /bin/sh -c "
        echo 'Container test started'
        echo 'Working directory: \$(pwd)'
        echo 'Mount points:'
        ls -la /test/
        echo ''
        echo 'Testing file creation:'
        echo 'test-$(date +%s)' > /test/deck_files/docker-test.txt
        echo 'test-$(date +%s)' > /test/logs/docker-test.log
        echo 'test-$(date +%s)' > /test/csv_files/docker-test.csv
        echo 'Files created in container'
        ls -la /test/*/docker-test.*
    "

echo ""
echo "=== Host File Check After Docker Test ==="
echo "Checking if files were created on host:"
for dir in deck_files logs csv_files; do
    echo "$dir:"
    if [ -f "$dir/docker-test.txt" ] || [ -f "$dir/docker-test.log" ] || [ -f "$dir/docker-test.csv" ]; then
        ls -la "$dir"/docker-test.*
    else
        echo "  No test files found"
    fi
done

# Test with the actual MTG image
echo ""
echo "=== MTG Deckbuilder Container Test ==="
echo "Testing with actual MTG deckbuilder image..."

# First check if image exists
if docker images | grep -q mtg-deckbuilder; then
    echo "MTG deckbuilder image found"
    
    docker run --rm \
        -v "$(pwd)/deck_files:/app/deck_files" \
        -v "$(pwd)/logs:/app/logs" \
        -v "$(pwd)/csv_files:/app/csv_files" \
        mtg-deckbuilder /bin/bash -c "
            echo 'MTG Container test'
            echo 'Working directory: \$(pwd)'
            echo 'Python path: \$(which python)'
            echo 'App directory contents:'
            ls -la /app/
            echo ''
            echo 'Mount point permissions:'
            ls -la /app/deck_files /app/logs /app/csv_files
            echo ''
            echo 'Testing file creation:'
            echo 'mtg-test-$(date +%s)' > /app/deck_files/mtg-test.txt
            echo 'mtg-test-$(date +%s)' > /app/logs/mtg-test.log
            echo 'mtg-test-$(date +%s)' > /app/csv_files/mtg-test.csv
            echo 'MTG test files created'
            
            # Try to run a quick Python test
            cd /app/code
            python -c 'import os; print(\"Python can access:\", os.listdir(\"/app\"))'
            python -c '
import os
from pathlib import Path
print(\"Testing Path operations:\")
deck_path = Path(\"/app/deck_files\")
print(f\"Deck path exists: {deck_path.exists()}\")
print(f\"Deck path writable: {os.access(deck_path, os.W_OK)}\")
test_file = deck_path / \"python-test.txt\"
try:
    test_file.write_text(\"Python test\")
    print(f\"Python write successful: {test_file.read_text()}\")
except Exception as e:
    print(f\"Python write failed: {e}\")
'
        "
else
    echo "MTG deckbuilder image not found. Building..."
    docker build -t mtg-deckbuilder .
fi

echo ""
echo "=== Final Host Check ==="
echo "Files in host directories after all tests:"
for dir in deck_files logs csv_files; do
    echo "$dir:"
    ls -la "$dir"/ 2>/dev/null || echo "  Directory empty or inaccessible"
    echo ""
done

# Cleanup test files
echo "=== Cleanup ==="
echo "Removing test files..."
rm -f deck_files/docker-test.* logs/docker-test.* csv_files/docker-test.*
rm -f deck_files/mtg-test.* logs/mtg-test.* csv_files/mtg-test.*
rm -f deck_files/python-test.* logs/python-test.* csv_files/python-test.*

echo "Diagnostics complete!"
