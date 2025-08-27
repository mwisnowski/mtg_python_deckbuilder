@echo off
setlocal ENABLEDELAYEDEXPANSION

echo MTG Python Deckbuilder - Web UI (Docker Hub)
echo ============================================

REM Create directories if they don't exist
if not exist "deck_files" mkdir deck_files
if not exist "logs" mkdir logs
if not exist "csv_files" mkdir csv_files
if not exist "config" mkdir config
if not exist "owned_cards" mkdir owned_cards

REM Flags (override by setting env vars before running)
if "%SHOW_LOGS%"=="" set SHOW_LOGS=1
if "%SHOW_DIAGNOSTICS%"=="" set SHOW_DIAGNOSTICS=1

echo Starting Web UI on http://localhost:8080
printf Flags: SHOW_LOGS=%SHOW_LOGS%  SHOW_DIAGNOSTICS=%SHOW_DIAGNOSTICS%

docker run --rm ^
  -p 8080:8080 ^
  -e SHOW_LOGS=%SHOW_LOGS% -e SHOW_DIAGNOSTICS=%SHOW_DIAGNOSTICS% ^
  -v "%cd%\deck_files:/app/deck_files" ^
  -v "%cd%\logs:/app/logs" ^
  -v "%cd%\csv_files:/app/csv_files" ^
  -v "%cd%\owned_cards:/app/owned_cards" ^
  -v "%cd%\config:/app/config" ^
  mwisnowski/mtg-python-deckbuilder:latest ^
  bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"

echo.
echo Open: http://localhost:8080
echo Tip: set SHOW_LOGS=0 or SHOW_DIAGNOSTICS=0 before running to hide those pages.
endlocal
