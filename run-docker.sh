#!/bin/bash
# MTG Deckbuilder Docker Runner Script for Linux/macOS

echo "MTG Deckbuilder Docker Helper"
echo "=============================="

show_help() {
    echo ""
    echo "Available commands:"
    echo "  ./run-docker.sh build    - Build the Docker image"
    echo "  ./run-docker.sh run      - Run the application with volume mounting"
    echo "  ./run-docker.sh compose  - Use docker-compose (recommended)"
    echo "  ./run-docker.sh clean    - Remove containers and images"
    echo "  ./run-docker.sh help     - Show this help"
    echo ""
}

case "$1" in
    "build")
        echo "Building MTG Deckbuilder Docker image..."
        docker build -t mtg-deckbuilder .
        if [ $? -eq 0 ]; then
            echo "Build successful!"
        else
            echo "Build failed!"
        fi
        ;;
    
    "run")
        echo "Running MTG Deckbuilder with volume mounting..."
        
        # Ensure local directories exist
        mkdir -p deck_files logs csv_files
        
        # Run with proper volume mounting
        docker run -it --rm \
            -v "$(pwd)/deck_files:/app/deck_files" \
            -v "$(pwd)/logs:/app/logs" \
            -v "$(pwd)/csv_files:/app/csv_files" \
            mtg-deckbuilder
        ;;
    
    "compose")
        echo "Running MTG Deckbuilder with Docker Compose..."
        
        # Ensure local directories exist
        mkdir -p deck_files logs csv_files
        
        docker-compose up --build
        ;;
    
    "clean")
        echo "Cleaning up Docker containers and images..."
        docker-compose down 2>/dev/null
        docker rmi mtg-deckbuilder 2>/dev/null
        docker system prune -f
        echo "Cleanup complete!"
        ;;
    
    "help"|*)
        show_help
        ;;
esac

echo ""
echo "Note: Your deck files, logs, and CSV files will be saved in the local directories"
echo "and will persist between Docker runs."
