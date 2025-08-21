#!/bin/bash
# Simple MTG Deckbuilder runner with proper interactivity

echo "MTG Deckbuilder - Quick Start"
echo "=============================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Create directories if they don't exist
echo -e "${GREEN}Setting up directories...${NC}"
mkdir -p deck_files logs csv_files

# Check which compose command is available
if command -v docker-compose &> /dev/null; then
    COMPOSE_CMD="docker-compose"
elif docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    echo "Error: Neither docker-compose nor 'docker compose' is available"
    exit 1
fi

echo -e "${GREEN}Using: $COMPOSE_CMD${NC}"
echo -e "${YELLOW}Starting MTG Deckbuilder...${NC}"
echo "Press Ctrl+C to exit when done"
echo ""

# Run with the interactive compose file
$COMPOSE_CMD -f docker-compose.interactive.yml run --rm mtg-deckbuilder-interactive
