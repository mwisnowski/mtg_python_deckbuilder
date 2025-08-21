#!/bin/bash
# MTG Deckbuilder Docker Runner for Linux Remote Host

set -e  # Exit on any error

echo "MTG Deckbuilder Docker Helper (Linux)"
echo "====================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_debug() {
    echo -e "${BLUE}[DEBUG]${NC} $1"
}

show_help() {
    echo ""
    echo -e "${YELLOW}Available commands:${NC}"
    echo "  ./run-docker-linux.sh setup           - Initial setup (create directories, check Docker)"
    echo "  ./run-docker-linux.sh build           - Build the Docker image"
    echo "  ./run-docker-linux.sh run             - Run with manual volume mounting"
    echo "  ./run-docker-linux.sh compose         - Use docker-compose run (recommended for interactive)"
    echo "  ./run-docker-linux.sh compose-build   - Build and run with docker-compose"
    echo "  ./run-docker-linux.sh compose-up      - Use docker-compose up (not recommended for interactive)"
    echo "  ./run-docker-linux.sh debug           - Run with debug info and volume verification"
    echo "  ./run-docker-linux.sh clean           - Remove containers and images"
    echo "  ./run-docker-linux.sh help            - Show this help"
    echo ""
    echo -e "${BLUE}For interactive applications like MTG Deckbuilder:${NC}"
    echo -e "${BLUE}  - Use 'compose' or 'run' commands${NC}"
    echo -e "${BLUE}  - Avoid 'compose-up' as it doesn't handle input properly${NC}"
}

setup_directories() {
    print_status "Setting up directories..."
    
    # Create directories with proper permissions
    mkdir -p deck_files logs csv_files
    
    # Set permissions to ensure Docker can write
    chmod 755 deck_files logs csv_files
    
    print_status "Current directory: $(pwd)"
    print_status "Directory structure:"
    ls -la | grep -E "(deck_files|logs|csv_files|^d)"
    
    echo ""
    print_status "Directory setup complete!"
}

check_docker() {
    print_status "Checking Docker installation..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_warning "docker-compose not found, trying docker compose..."
        if ! docker compose version &> /dev/null; then
            print_error "Neither docker-compose nor 'docker compose' is available"
            exit 1
        else
            COMPOSE_CMD="docker compose"
        fi
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    print_status "Docker is available"
    print_status "Compose command: $COMPOSE_CMD"
}

case "$1" in
    "setup")
        check_docker
        setup_directories
        print_status "Setup complete! You can now run: ./run-docker-linux.sh compose"
        ;;
    
    "build")
        print_status "Building MTG Deckbuilder Docker image..."
        docker build -t mtg-deckbuilder .
        if [ $? -eq 0 ]; then
            print_status "Build successful!"
        else
            print_error "Build failed!"
            exit 1
        fi
        ;;
    
    "run")
        print_status "Running MTG Deckbuilder with manual volume mounting..."
        
        # Ensure directories exist
        setup_directories
        
        print_debug "Volume mounts:"
        print_debug "  $(pwd)/deck_files -> /app/deck_files"
        print_debug "  $(pwd)/logs -> /app/logs"
        print_debug "  $(pwd)/csv_files -> /app/csv_files"
        
        # Run with proper volume mounting
        docker run -it --rm \
            -v "$(pwd)/deck_files:/app/deck_files" \
            -v "$(pwd)/logs:/app/logs" \
            -v "$(pwd)/csv_files:/app/csv_files" \
            -e PYTHONUNBUFFERED=1 \
            -e TERM=xterm-256color \
            mtg-deckbuilder
        ;;
    
    "compose")
        print_status "Running MTG Deckbuilder with Docker Compose..."
        
        # Ensure directories exist
        setup_directories
        
        # Check for compose command
        check_docker
        
        print_debug "Using compose command: $COMPOSE_CMD"
        print_debug "Working directory: $(pwd)"
        
        print_status "Starting interactive session..."
        print_warning "Use Ctrl+C to exit when done"
        
        # Run with compose in interactive mode
        $COMPOSE_CMD run --rm mtg-deckbuilder
        ;;
    
    "compose-build")
        print_status "Building and running MTG Deckbuilder with Docker Compose..."
        
        # Ensure directories exist
        setup_directories
        
        # Check for compose command
        check_docker
        
        print_debug "Using compose command: $COMPOSE_CMD"
        print_debug "Working directory: $(pwd)"
        
        print_status "Building image and starting interactive session..."
        print_warning "Use Ctrl+C to exit when done"
        
        # Build and run with compose in interactive mode
        $COMPOSE_CMD build
        $COMPOSE_CMD run --rm mtg-deckbuilder
        ;;
    
    "compose-up")
        print_status "Running MTG Deckbuilder with Docker Compose UP (not recommended for interactive apps)..."
        
        # Ensure directories exist
        setup_directories
        
        # Check for compose command
        check_docker
        
        print_debug "Using compose command: $COMPOSE_CMD"
        print_debug "Working directory: $(pwd)"
        
        print_warning "This may not work properly for interactive applications!"
        print_warning "Use 'compose' command instead for better interactivity"
        
        # Run with compose
        $COMPOSE_CMD up --build
        ;;
    
    "debug")
        print_status "Running in debug mode..."
        
        setup_directories
        
        print_debug "=== DEBUG INFO ==="
        print_debug "Current user: $(whoami)"
        print_debug "Current directory: $(pwd)"
        print_debug "Directory permissions:"
        ls -la deck_files logs csv_files 2>/dev/null || print_warning "Some directories don't exist yet"
        
        print_debug "=== DOCKER INFO ==="
        docker --version
        docker info | grep -E "(Operating System|Architecture)"
        
        print_debug "=== RUNNING CONTAINER ==="
        docker run -it --rm \
            -v "$(pwd)/deck_files:/app/deck_files" \
            -v "$(pwd)/logs:/app/logs" \
            -v "$(pwd)/csv_files:/app/csv_files" \
            -e PYTHONUNBUFFERED=1 \
            -e TERM=xterm-256color \
            mtg-deckbuilder /bin/bash -c "
                echo 'Container info:'
                echo 'Working dir: \$(pwd)'
                echo 'Mount points:'
                ls -la /app/
                echo 'Testing file creation:'
                touch /app/deck_files/test_file.txt
                echo 'File created: \$(ls -la /app/deck_files/test_file.txt)'
                echo 'Starting application...'
                python main.py
            "
        ;;
    
    "clean")
        print_status "Cleaning up Docker containers and images..."
        
        check_docker
        
        # Stop and remove containers
        $COMPOSE_CMD down 2>/dev/null || true
        docker stop mtg-deckbuilder 2>/dev/null || true
        docker rm mtg-deckbuilder 2>/dev/null || true
        
        # Remove image
        docker rmi mtg-deckbuilder 2>/dev/null || true
        
        # Clean up unused resources
        docker system prune -f
        
        print_status "Cleanup complete!"
        ;;
    
    "help"|*)
        show_help
        ;;
esac

echo ""
echo -e "${BLUE}Note: Your deck files, logs, and CSV files will be saved in:${NC}"
echo -e "${BLUE}  $(pwd)/deck_files${NC}"
echo -e "${BLUE}  $(pwd)/logs${NC}"
echo -e "${BLUE}  $(pwd)/csv_files${NC}"
