@echo off
REM ECLI Metadata Extractor - Docker Setup Script for Windows
REM This script builds and starts the Docker containers

echo ========================================
echo ECLI Metadata Extractor - Docker Setup
echo ========================================
echo.

REM Check if Docker is running
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Docker is not running or not installed!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

echo Docker is running. Starting setup...
echo.

REM Create necessary directories
if not exist "jsons" mkdir jsons
if not exist "backups" mkdir backups

echo Building Docker containers...
docker-compose build

if %errorlevel% neq 0 (
    echo ERROR: Failed to build Docker containers!
    pause
    exit /b 1
)

echo.
echo Starting services...
docker-compose up -d

if %errorlevel% neq 0 (
    echo ERROR: Failed to start services!
    pause
    exit /b 1
)

echo.
echo Waiting for PostgreSQL to be ready...
:wait_loop
docker-compose exec postgres pg_isready -U postgres -d ecli_rag_db >nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 2 /nobreak >nul
    goto wait_loop
)

echo.
echo ========================================
echo SUCCESS! Docker setup complete!
echo ========================================
echo.
echo Services running:
echo - PostgreSQL: localhost:5432
echo   Database: ecli_rag_db
echo   User: postgres
echo   Password: As!101010
echo.
echo - pgAdmin: http://localhost:8080
echo   Email: admin@ecli.local
echo   Password: admin123
echo.
echo Next steps:
echo 1. Copy your JSON files to the 'jsons' folder
echo 2. Run: docker-compose exec postgres python /app/json_to_postgres_loader.py
echo 3. Run: docker-compose exec postgres python /app/corpus_analyzer.py
echo.
echo To stop: docker-compose down
echo To view logs: docker-compose logs -f
echo.
pause