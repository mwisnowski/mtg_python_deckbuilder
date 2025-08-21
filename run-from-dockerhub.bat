@echo off
echo MTG Python Deckbuilder - Docker Hub Runner
echo ===========================================

REM Create directories if they don't exist
if not exist "deck_files" mkdir deck_files
if not exist "logs" mkdir logs
if not exist "csv_files" mkdir csv_files

echo Starting MTG Python Deckbuilder from Docker Hub...
echo Your files will be saved in the current directory:
echo   - deck_files\: Your completed decks
echo   - logs\: Application logs
echo   - csv_files\: Card database files
echo.

REM Run the Docker container with proper volume mounts
docker run -it --rm ^
  -v "%cd%\deck_files:/app/deck_files" ^
  -v "%cd%\logs:/app/logs" ^
  -v "%cd%\csv_files:/app/csv_files" ^
  mwisnowski/mtg-python-deckbuilder:latest

echo.
echo MTG Python Deckbuilder session ended.
echo Your files are saved in: %cd%
pause
