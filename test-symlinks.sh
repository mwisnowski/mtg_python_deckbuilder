#!/bin/bash
# Test symbolic links in MTG Deckbuilder Docker container

echo "=== MTG Deckbuilder Symbolic Link Test ==="

# Ensure directories exist
mkdir -p deck_files logs csv_files

# Build the image with symbolic links
echo "Building MTG Deckbuilder with symbolic links..."
docker build -t mtg-deckbuilder .

# Test the symbolic link setup
echo ""
echo "Testing symbolic links in container..."
docker run --rm \
    -v "$(pwd)/deck_files:/app/deck_files" \
    -v "$(pwd)/logs:/app/logs" \
    -v "$(pwd)/csv_files:/app/csv_files" \
    mtg-deckbuilder /bin/bash -c "
        echo 'Working directory: \$(pwd)'
        echo ''
        echo 'Checking symbolic links:'
        ls -la deck_files logs csv_files
        echo ''
        echo 'Testing file creation via symlinks:'
        echo 'symlink-test-\$(date +%s)' > deck_files/symlink-test.txt
        echo 'symlink-test-\$(date +%s)' > logs/symlink-test.log  
        echo 'symlink-test-\$(date +%s)' > csv_files/symlink-test.csv
        echo 'Files created via symlinks'
        echo ''
        echo 'Verifying files exist:'
        ls -la deck_files/ logs/ csv_files/
    "

echo ""
echo "Checking files on host:"
echo "deck_files:"
ls -la deck_files/
echo "logs:"
ls -la logs/
echo "csv_files:"
ls -la csv_files/

# Cleanup
echo ""
echo "Cleaning up test files..."
rm -f deck_files/symlink-test.* logs/symlink-test.* csv_files/symlink-test.*

echo "Test complete!"
