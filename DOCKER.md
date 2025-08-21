# Docker Guide for MTG Python Deckbuilder

A comprehensive guide for running the MTG Python Deckbuilder in Docker containers with full file persistence and cross-platform support.

## 🚀 Quick Start

### Linux/macOS/Remote Host
```bash
# Make scripts executable (one time only)
chmod +x quick-start.sh run-docker.sh

# Simplest method - just run this:
./quick-start.sh

# Or use the full script with options:
./run-docker.sh compose
```

### Windows (PowerShell)
```powershell
# Run with Docker Compose (recommended)
.\run-docker.ps1 compose

# Or manual Docker run
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    mtg-deckbuilder
```

## 📋 Prerequisites

- **Docker** installed and running
- **Docker Compose** (usually included with Docker)
- Basic terminal/command line knowledge

## 🔧 Available Commands

### Quick Start Scripts

| Script | Platform | Description |
|--------|----------|-------------|
| `./quick-start.sh` | Linux/macOS | Simplest way to run the application |
| `.\run-docker.ps1 compose` | Windows | PowerShell equivalent |

### Full Featured Scripts

| Command | Description |
|---------|-------------|
| `./run-docker.sh setup` | Create directories and check Docker installation |
| `./run-docker.sh build` | Build the Docker image |
| `./run-docker.sh compose` | Run with Docker Compose (recommended) |
| `./run-docker.sh run` | Run with manual volume mounting |
| `./run-docker.sh clean` | Remove containers and images |

## 🗂️ File Persistence

Your files are automatically saved to local directories that persist between runs:

```
mtg_python_deckbuilder/
├── deck_files/          # Your saved decks (CSV and TXT files)
├── logs/               # Application logs and debug info
├── csv_files/          # Card database and color-sorted files
└── ...
```

### How It Works

The Docker container uses **volume mounting** to map container directories to your local filesystem:

- Container path `/app/deck_files` ↔ Host path `./deck_files`
- Container path `/app/logs` ↔ Host path `./logs`
- Container path `/app/csv_files` ↔ Host path `./csv_files`

When the application saves files, they appear in your local directories and remain there after the container stops.

## 🎮 Interactive Application Requirements

The MTG Deckbuilder is an **interactive application** that uses menus and requires keyboard input.

### ✅ Commands That Work
- `docker compose run --rm mtg-deckbuilder`
- `docker run -it --rm mtg-deckbuilder`
- `./quick-start.sh`
- Helper scripts with `compose` command

### ❌ Commands That Don't Work
- `docker compose up` (runs in background, no interaction)
- `docker run` without `-it` flags
- Any command without proper TTY allocation

### Why the Difference?
- **`docker compose run`**: Creates new container with terminal attachment
- **`docker compose up`**: Starts service in background without terminal

## 🔨 Manual Docker Commands

### Build the Image
```bash
docker build -t mtg-deckbuilder .
```

### Run with Full Volume Mounting

**Linux/macOS:**
```bash
docker run -it --rm \
    -v "$(pwd)/deck_files:/app/deck_files" \
    -v "$(pwd)/logs:/app/logs" \
    -v "$(pwd)/csv_files:/app/csv_files" \
    mtg-deckbuilder
```

**Windows PowerShell:**
```powershell
docker run -it --rm `
    -v "${PWD}/deck_files:/app/deck_files" `
    -v "${PWD}/logs:/app/logs" `
    -v "${PWD}/csv_files:/app/csv_files" `
    mtg-deckbuilder
```

## 📁 Docker Compose Files

The project includes two Docker Compose configurations:

### `docker-compose.yml` (Main)
- Standard configuration
- Container name: `mtg-deckbuilder-main`
- Use with: `docker compose run --rm mtg-deckbuilder`

Both files provide the same functionality and file persistence.

## 🐛 Troubleshooting

### Files Not Saving?

1. **Check volume mounts**: Ensure you see `-v` flags in your docker command
2. **Verify directories exist**: Scripts automatically create needed directories
3. **Check permissions**: Ensure you have write access to the project directory
4. **Use correct command**: Use `docker compose run`, not `docker compose up`

### Application Won't Start Interactively?

1. **Use the right command**: `docker compose run --rm mtg-deckbuilder`
2. **Check TTY allocation**: Ensure `-it` flags are present in manual commands
3. **Avoid background mode**: Don't use `docker compose up` for interactive apps

### Permission Issues?

Files created by Docker may be owned by `root`. This is normal on Linux systems.

### Container Build Fails?

1. **Update Docker**: Ensure you have a recent version
2. **Clear cache**: Run `docker system prune -f`
3. **Check network**: Ensure Docker can download dependencies

### Starting Fresh

**Complete cleanup:**
```bash
# Stop all containers
docker compose down

# Remove image
docker rmi mtg-deckbuilder

# Clean up system
docker system prune -f

# Rebuild
docker compose build
```

## 🔍 Verifying Everything Works

After running the application:

1. **Create or modify some data** (run setup, build a deck, etc.)
2. **Exit the container** (Ctrl+C or select Quit)
3. **Check your local directories**:
   ```bash
   ls -la deck_files/   # Should show any decks you created
   ls -la logs/         # Should show log files
   ls -la csv_files/    # Should show card database files
   ```
4. **Run again** - your data should still be there!

## 🎯 Best Practices

1. **Use the quick-start script** for simplest experience
2. **Always use `docker compose run`** for interactive applications
3. **Keep your project directory organized** - files persist locally
4. **Regularly backup your `deck_files/`** if you create valuable decks
5. **Use `clean` commands** to free up disk space when needed

## 🌟 Benefits of Docker Approach

- ✅ **Consistent environment** across different machines
- ✅ **No Python installation required** on host system
- ✅ **Isolated dependencies** - won't conflict with other projects
- ✅ **Easy sharing** - others can run your setup instantly
- ✅ **Cross-platform** - works on Windows, macOS, and Linux
- ✅ **File persistence** - your work is saved locally
- ✅ **Easy cleanup** - remove everything with one command

---

**Need help?** Check the troubleshooting section above or refer to the helper script help:
```bash
./run-docker.sh help
```
