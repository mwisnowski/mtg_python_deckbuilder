# Docker Usage Guide for MTG Deckbuilder

## Quick Start (Recommended)

### Windows (PowerShell)
```powershell
# Run with Docker Compose (easiest method)
.\run-docker.ps1 compose
```

### Linux/macOS
```bash
# Make script executable (one time only)
chmod +x run-docker.sh

# Run with Docker Compose
./run-docker.sh compose
```

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
