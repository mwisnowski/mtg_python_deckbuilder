# Docker Usage Guide for MTG Deckbuilder

## Quick Start (Recommended)

### Linux/Remote Host (Interactive Applications)
```bash
# Make scripts executable (one time only)
chmod +x quick-start.sh run-docker-linux.sh

# Simplest method - just run this:
./quick-start.sh

# Or use the full script with more options:
./run-docker-linux.sh compose
```

### Windows (PowerShell)
```powershell
# Run with Docker Compose
.\run-docker.ps1 compose
```

## Important: Interactive Applications & Docker Compose

**Your MTG Deckbuilder is an interactive application** that uses menus and requires keyboard input. This creates special requirements:

### ✅ What Works for Interactive Apps:
- `docker run -it` (manual)
- `docker-compose run` (recommended)
- `./quick-start.sh` (easiest)

### ❌ What Doesn't Work:
- `docker-compose up` (runs in background, no interaction)
- Running without `-it` flags

### Why the Difference?

- **`docker-compose up`**: Starts services in the background, doesn't attach to your terminal
- **`docker-compose run`**: Creates a new container and attaches to your terminal for interaction

## Manual Docker Commands

### Windows PowerShell
```powershell
# Build the image
docker build -t mtg-deckbuilder .

# Run with volume mounting for file persistence
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    mtg-deckbuilder
```

### Linux/macOS/Git Bash
```bash
# Build the image
docker build -t mtg-deckbuilder .

# Run with volume mounting for file persistence
docker run -it --rm \
    -v "$(pwd)/deck_files:/app/deck_files" \
    -v "$(pwd)/logs:/app/logs" \
    -v "$(pwd)/csv_files:/app/csv_files" \
    mtg-deckbuilder
```

## File Persistence Explained

The key to saving your files is **volume mounting**. Here's what happens:

### Without Volume Mounting (Bad)
- Files are saved inside the container
- When container stops, files are lost forever
- Example: `docker run -it mtg-deckbuilder` ❌

### With Volume Mounting (Good)
- Files are saved to your local directories
- Files persist between container runs
- Local directories are "mounted" into the container
- Example: `docker run -it -v "./deck_files:/app/deck_files" mtg-deckbuilder` ✅

## Directory Structure After Running

After running the Docker container, you'll have these local directories:

```
mtg_python_deckbuilder/
├── deck_files/          # Your saved decks (CSV and TXT files)
├── logs/               # Application logs
├── csv_files/          # Card database files
└── ...
```

## Troubleshooting

### Files Still Not Saving?

1. **Check directory creation**: The helper scripts automatically create the needed directories
2. **Verify volume mounts**: Look for `-v` flags in your docker run command
3. **Check permissions**: Make sure you have write access to the local directories

### Starting Fresh

```powershell
# Windows - Clean up everything
.\run-docker.ps1 clean

# Or manually
docker-compose down
docker rmi mtg-deckbuilder
```

### Container Won't Start

1. Make sure Docker Desktop is running
2. Try rebuilding: `.\run-docker.ps1 build`
3. Check for port conflicts
4. Review Docker logs: `docker logs mtg-deckbuilder`

## Helper Script Commands

### Windows PowerShell
```powershell
.\run-docker.ps1 build     # Build the Docker image
.\run-docker.ps1 run       # Run with manual volume mounting
.\run-docker.ps1 compose   # Run with Docker Compose (recommended)
.\run-docker.ps1 clean     # Clean up containers and images
.\run-docker.ps1 help      # Show help
```

### Linux/macOS
```bash
./run-docker.sh build     # Build the Docker image
./run-docker.sh run       # Run with manual volume mounting
./run-docker.sh compose   # Run with Docker Compose (recommended)
./run-docker.sh clean     # Clean up containers and images
./run-docker.sh help      # Show help
```

## Why Docker Compose is Recommended

Docker Compose offers several advantages:

1. **Simpler commands**: Just `docker-compose up`
2. **Configuration in file**: All settings stored in `docker-compose.yml`
3. **Automatic cleanup**: Containers are removed when stopped
4. **Consistent behavior**: Same setup every time

## Verifying File Persistence

After running the application and creating/saving files:

1. Exit the Docker container
2. Check your local directories:
   ```powershell
   ls deck_files    # Should show your saved deck files
   ls logs         # Should show log files
   ls csv_files    # Should show card database files
   ```
3. Run the container again - your files should still be there!
