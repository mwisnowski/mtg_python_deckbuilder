@echo off
echo MTG Python Deckbuilder - Docker Hub Runner
echo ===========================================

REM Create directories if they don't exist
if not exist "deck_files" mkdir deck_files
if not exist "logs" mkdir logs
if not exist "csv_files" mkdir csv_files
if not exist "config" mkdir config

echo Starting MTG Python Deckbuilder from Docker Hub...
echo Your files will be saved in the current directory:
echo   - deck_files\: Your completed decks
echo   - logs\: Application logs
echo   - csv_files\: Card database files
echo   - config\: JSON configs for headless runs (e.g., deck.json)
echo.

REM Run the Docker container with proper volume mounts
docker run -it --rm ^
  -v "%cd%\deck_files:/app/deck_files" ^
  -v "%cd%\logs:/app/logs" ^
  -v "%cd%\csv_files:/app/csv_files" ^
  -v "%cd%\config:/app/config" ^
  mwisnowski/mtg-python-deckbuilder:latest

echo.
echo MTG Python Deckbuilder session ended.
echo Your files are saved in: %cd%
echo.
echo Tips:
echo   - For headless: set environment variables, e.g. -e DECK_MODE=headless -e DECK_CONFIG=/app/config/deck.json
echo   - If the container seems to use an old config, mount the config folder (done above) or prune anonymous volumes.
pause
