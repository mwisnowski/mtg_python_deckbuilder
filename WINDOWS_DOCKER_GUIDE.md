# MTG Python Deckbuilder - Windows Docker Desktop Guide

## Prerequisites
- [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/) installed and running
- Windows 10/11 with WSL2 enabled (Docker Desktop will guide you through this)

## ⭐ Recommended: Method 1 - PowerShell

**Why PowerShell is recommended**:
- ✅ Works consistently across all Docker Desktop versions
- ✅ Handles interactive terminals reliably  
- ✅ Simple copy-paste commands
- ✅ No GUI configuration needed

## Method 1: PowerShell (Recommended)

### Step 1: Open PowerShell
- Press `Win + X` and select "Windows PowerShell" or "Terminal"
- Or search for "PowerShell" in the Start menu

### Step 2: Create and Navigate to Your Workspace
```powershell
# Create a directory for your MTG decks
mkdir C:\mtg-decks
cd C:\mtg-decks
```

### Step 3: Run the Application
```powershell
# Option A: Use the helper script (easiest)
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/mwisnowski/mtg_python_deckbuilder/main/run-from-dockerhub.bat" -OutFile "run-from-dockerhub.bat"
.\run-from-dockerhub.bat

# Option B: Manual command
docker run -it --rm `
  -v "${PWD}/deck_files:/app/deck_files" `
  -v "${PWD}/logs:/app/logs" `
  -v "${PWD}/csv_files:/app/csv_files" `
  mwisnowski/mtg-python-deckbuilder:latest
```

## Method 2: Command Prompt
```cmd
REM Create and navigate to workspace
mkdir C:\mtg-decks
cd C:\mtg-decks

REM Run the application
docker run -it --rm ^
  -v "%cd%\deck_files:/app/deck_files" ^
  -v "%cd%\logs:/app/logs" ^
  -v "%cd%\csv_files:/app/csv_files" ^
  mwisnowski/mtg-python-deckbuilder:latest
```

## Method 3: Docker Desktop GUI (Alternative)

**Note**: This method can be tricky due to Docker Desktop interface changes. **Method 1 (PowerShell) is recommended** for reliability.

### Step 1: Pull the Image
1. Open Docker Desktop
2. Go to **Images** tab
3. Click **"Search"** and enter: `mwisnowski/mtg-python-deckbuilder`
4. Click **"Pull"** next to the image

### Step 2: Create Volume Directories
Create these folders on your computer:
```
C:\mtg-decks\
├── deck_files\
├── logs\
└── csv_files\
```

### Step 3: Run Container
1. In Docker Desktop, go to **Images** tab
2. Find `mwisnowski/mtg-python-deckbuilder:latest`
3. Click the **"Run"** button (▶️)
4. In the run dialog:
   - **Container name**: `mtg-deckbuilder` (optional)
   - **Ports**: Leave empty
   - **Volumes**: Click "+" or "Add" to add these three mappings:
     - Host path: `C:\mtg-decks\deck_files` → Container path: `/app/deck_files`
     - Host path: `C:\mtg-decks\logs` → Container path: `/app/logs`
     - Host path: `C:\mtg-decks\csv_files` → Container path: `/app/csv_files`
   - **Environment variables**: Leave empty
   - Look for options like:
     - ✅ "Interactive" or "Attach STDIN" 
     - ✅ "Allocate a pseudo-TTY" or "TTY"
     - ✅ "Auto-remove" or "Remove container when stopped"
     
   **Note**: The exact wording and location of these options varies by Docker Desktop version. If you don't see these options, the PowerShell method below is recommended.

5. Click **"Run"**

### Alternative: Use "Optional settings" or "Advanced"
Some Docker Desktop versions put these options under:
- "Optional settings" dropdown
- "Advanced" section
- "Runtime settings"

If you can't find Interactive/TTY options in the GUI, **use Method 1 (PowerShell) instead** - it's more reliable.

### Step 4: Access Terminal
1. Go to **Containers** tab in Docker Desktop
2. Click on your running `mtg-deckbuilder` container
3. Click **"Open in terminal"** or the terminal icon
4. The MTG Python Deckbuilder should start automatically

## Troubleshooting

### Issue: "Docker daemon not running"
**Solution**: Make sure Docker Desktop is running. Look for the Docker whale icon in your system tray.

### Issue: "Permission denied" or file access errors
**Solution**: 
1. Make sure Docker Desktop has access to your C: drive
2. Go to Docker Desktop → Settings → Resources → File Sharing
3. Add your `C:\mtg-decks` folder to the shared directories

### Issue: Files not persisting
**Solution**: Double-check your volume mappings are correct:
- Host path should be your actual Windows path (e.g., `C:\mtg-decks\deck_files`)
- Container path should be exactly `/app/deck_files` (with forward slashes)

### Issue: Can't interact with menus
**Solution**: 
- **Preferred**: Use PowerShell method instead of Docker Desktop GUI
- **GUI Alternative**: Look for "Interactive", "STDIN", "TTY", or "Terminal" options in the run dialog
- **Last resort**: After container starts, click on it in the Containers tab and look for "Open in terminal" or terminal icon

### Issue: Can't find Interactive/TTY options in Docker Desktop
**Solution**: Docker Desktop versions vary significantly. If you can't find these options:
1. Use **Method 1 (PowerShell)** instead - it's more reliable
2. Or try running this command in Docker Desktop's built-in terminal:
   ```bash
   docker run -it --rm -v "C:/mtg-decks/deck_files:/app/deck_files" -v "C:/mtg-decks/logs:/app/logs" -v "C:/mtg-decks/csv_files:/app/csv_files" mwisnowski/mtg-python-deckbuilder:latest
   ```

## Expected File Structure

After running, your `C:\mtg-decks\` folder will contain:
```
C:\mtg-decks\
├── deck_files\              # Your completed decks (.csv and .txt files)
│   ├── Atraxa_Superfriends_20250821.csv
│   ├── Atraxa_Superfriends_20250821.txt
│   └── ...
├── logs\                    # Application logs
│   └── deck_builder.log
└── csv_files\               # Card database files
    ├── commander_cards.csv
    ├── white_cards.csv
    └── ...
```

## Tips for Windows Users

1. **Use PowerShell over Command Prompt** - it has better Unicode support for card names
2. **Create a desktop shortcut** - Save the PowerShell command as a `.ps1` file for easy access
3. **Antivirus exceptions** - Add your `C:\mtg-decks` folder to antivirus exceptions if file operations are slow
4. **WSL2 backend** - Use WSL2 backend in Docker Desktop for better performance

## One-Click Setup Script

Save this as `setup-mtg-deckbuilder.ps1`:

```powershell
# MTG Python Deckbuilder - One-Click Setup for Windows
Write-Host "Setting up MTG Python Deckbuilder..." -ForegroundColor Green

# Create directories
$baseDir = "C:\mtg-decks"
New-Item -ItemType Directory -Force -Path "$baseDir\deck_files" | Out-Null
New-Item -ItemType Directory -Force -Path "$baseDir\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "$baseDir\csv_files" | Out-Null

Set-Location $baseDir

Write-Host "Pulling latest Docker image..." -ForegroundColor Yellow
docker pull mwisnowski/mtg-python-deckbuilder:latest

Write-Host "Starting MTG Python Deckbuilder..." -ForegroundColor Green
Write-Host "Your files will be saved in: $baseDir" -ForegroundColor Cyan

docker run -it --rm `
  -v "${baseDir}\deck_files:/app/deck_files" `
  -v "${baseDir}\logs:/app/logs" `
  -v "${baseDir}\csv_files:/app/csv_files" `
  mwisnowski/mtg-python-deckbuilder:latest

Write-Host "Session ended. Files saved in: $baseDir" -ForegroundColor Green
```

Then run with: `powershell -ExecutionPolicy Bypass -File setup-mtg-deckbuilder.ps1`
