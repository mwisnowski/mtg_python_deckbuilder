# MTG Deckbuilder Docker Runner Script
# This script provides easy commands to run the MTG Deckbuilder in Docker with proper volume mounting

Write-Host "MTG Deckbuilder Docker Helper" -ForegroundColor Green
Write-Host "==============================" -ForegroundColor Green

function Show-Help {
    Write-Host ""
    Write-Host "Available commands:" -ForegroundColor Yellow
    Write-Host "  .\run-docker.ps1 build    - Build the Docker image"
    Write-Host "  .\run-docker.ps1 run      - Run the application with volume mounting"
    Write-Host "  .\run-docker.ps1 compose  - Use docker-compose (recommended)"
    Write-Host "  .\run-docker.ps1 clean    - Remove containers and images"
    Write-Host "  .\run-docker.ps1 help     - Show this help"
    Write-Host ""
}

# Get command line argument
$command = $args[0]

switch ($command) {
    "build" {
        Write-Host "Building MTG Deckbuilder Docker image..." -ForegroundColor Yellow
        docker build -t mtg-deckbuilder .
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Build successful!" -ForegroundColor Green
        } else {
            Write-Host "Build failed!" -ForegroundColor Red
        }
    }
    
    "run" {
        Write-Host "Running MTG Deckbuilder with volume mounting..." -ForegroundColor Yellow
        
        # Ensure local directories exist
        if (!(Test-Path "deck_files")) { New-Item -ItemType Directory -Path "deck_files" }
        if (!(Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" }
        if (!(Test-Path "csv_files")) { New-Item -ItemType Directory -Path "csv_files" }
        
        # Run with proper volume mounting
        docker run -it --rm `
            -v "${PWD}/deck_files:/app/deck_files" `
            -v "${PWD}/logs:/app/logs" `
            -v "${PWD}/csv_files:/app/csv_files" `
            mtg-deckbuilder
    }
    
    "compose" {
        Write-Host "Running MTG Deckbuilder with Docker Compose..." -ForegroundColor Yellow
        
        # Ensure local directories exist
        if (!(Test-Path "deck_files")) { New-Item -ItemType Directory -Path "deck_files" }
        if (!(Test-Path "logs")) { New-Item -ItemType Directory -Path "logs" }
        if (!(Test-Path "csv_files")) { New-Item -ItemType Directory -Path "csv_files" }
        
        docker-compose up --build
    }
    
    "clean" {
        Write-Host "Cleaning up Docker containers and images..." -ForegroundColor Yellow
        docker-compose down 2>$null
        docker rmi mtg-deckbuilder 2>$null
        docker system prune -f
        Write-Host "Cleanup complete!" -ForegroundColor Green
    }
    
    "help" {
        Show-Help
    }
    
    default {
        Write-Host "Invalid command: $command" -ForegroundColor Red
        Show-Help
    }
}

Write-Host ""
Write-Host "Note: Your deck files, logs, and CSV files will be saved in the local directories" -ForegroundColor Cyan
Write-Host "and will persist between Docker runs." -ForegroundColor Cyan
