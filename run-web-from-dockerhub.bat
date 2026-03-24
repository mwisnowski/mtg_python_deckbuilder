@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Primary entry point for the MTG Python Deckbuilder Web UI from Docker Hub.
REM Override any flag by setting it as an environment variable before running:
REM   set THEME=light
REM   set ENABLE_BUDGET_MODE=0

echo MTG Python Deckbuilder - Web UI (Docker Hub)
echo ============================================

REM Create directories if they don't exist
if not exist "deck_files" mkdir deck_files
if not exist "logs" mkdir logs
if not exist "csv_files" mkdir csv_files
if not exist "config" mkdir config
if not exist "owned_cards" mkdir owned_cards

REM --- Core UI flags ---
if "%SHOW_LOGS%"=="" set SHOW_LOGS=1
if "%SHOW_DIAGNOSTICS%"=="" set SHOW_DIAGNOSTICS=1
if "%WEB_VIRTUALIZE%"=="" set WEB_VIRTUALIZE=1

REM --- Theming (system|light|dark) ---
if "%ENABLE_THEMES%"=="" set ENABLE_THEMES=1
if "%THEME%"=="" set THEME=dark

REM --- Budget Mode ---
if "%ENABLE_BUDGET_MODE%"=="" set ENABLE_BUDGET_MODE=1
if "%PRICE_LAZY_REFRESH%"=="" set PRICE_LAZY_REFRESH=1

REM --- Builder features ---
if "%ENABLE_BATCH_BUILD%"=="" set ENABLE_BATCH_BUILD=1
if "%WEB_STAGE_ORDER%"=="" set WEB_STAGE_ORDER=new
if "%WEB_IDEALS_UI%"=="" set WEB_IDEALS_UI=slider
if "%ALLOW_MUST_HAVES%"=="" set ALLOW_MUST_HAVES=1
if "%ENABLE_PARTNER_MECHANICS%"=="" set ENABLE_PARTNER_MECHANICS=1

REM --- Theme catalog badges ---
if "%SHOW_THEME_QUALITY_BADGES%"=="" set SHOW_THEME_QUALITY_BADGES=1
if "%SHOW_THEME_POOL_BADGES%"=="" set SHOW_THEME_POOL_BADGES=1
if "%SHOW_THEME_POPULARITY_BADGES%"=="" set SHOW_THEME_POPULARITY_BADGES=1
if "%SHOW_THEME_FILTERS%"=="" set SHOW_THEME_FILTERS=1

echo Starting Web UI on http://localhost:8080
echo Flags: SHOW_LOGS=%SHOW_LOGS%  SHOW_DIAGNOSTICS=%SHOW_DIAGNOSTICS%  WEB_VIRTUALIZE=%WEB_VIRTUALIZE%  THEME=%THEME%
echo        ENABLE_BUDGET_MODE=%ENABLE_BUDGET_MODE%  ENABLE_BATCH_BUILD=%ENABLE_BATCH_BUILD%  WEB_STAGE_ORDER=%WEB_STAGE_ORDER%

docker run --rm ^
  -p 8080:8080 ^
  -e SHOW_LOGS=%SHOW_LOGS% -e SHOW_DIAGNOSTICS=%SHOW_DIAGNOSTICS% -e WEB_VIRTUALIZE=%WEB_VIRTUALIZE% ^
  -e ENABLE_THEMES=%ENABLE_THEMES% -e THEME=%THEME% ^
  -e ENABLE_BUDGET_MODE=%ENABLE_BUDGET_MODE% -e PRICE_LAZY_REFRESH=%PRICE_LAZY_REFRESH% ^
  -e ENABLE_BATCH_BUILD=%ENABLE_BATCH_BUILD% -e WEB_STAGE_ORDER=%WEB_STAGE_ORDER% -e WEB_IDEALS_UI=%WEB_IDEALS_UI% ^
  -e ALLOW_MUST_HAVES=%ALLOW_MUST_HAVES% -e ENABLE_PARTNER_MECHANICS=%ENABLE_PARTNER_MECHANICS% ^
  -e SHOW_THEME_QUALITY_BADGES=%SHOW_THEME_QUALITY_BADGES% -e SHOW_THEME_POOL_BADGES=%SHOW_THEME_POOL_BADGES% ^
  -e SHOW_THEME_POPULARITY_BADGES=%SHOW_THEME_POPULARITY_BADGES% -e SHOW_THEME_FILTERS=%SHOW_THEME_FILTERS% ^
  -v "%cd%\deck_files:/app/deck_files" ^
  -v "%cd%\logs:/app/logs" ^
  -v "%cd%\csv_files:/app/csv_files" ^
  -v "%cd%\owned_cards:/app/owned_cards" ^
  -v "%cd%\config:/app/config" ^
  mwisnowski/mtg-python-deckbuilder:latest ^
  bash -lc "cd /app && uvicorn code.web.app:app --host 0.0.0.0 --port 8080"

echo.
echo Open: http://localhost:8080
echo Tips:
echo   set THEME=light^|dark^|system before running to change the theme
echo   set ENABLE_BUDGET_MODE=0 to disable budget controls
echo   set SHOW_LOGS=0 or SHOW_DIAGNOSTICS=0 to hide those pages
endlocal
