@echo off
echo Setting up reMarkable Dashboard Generator...
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed or not in PATH
    echo Please install Python 3.8 or higher from https://python.org
    pause
    exit /b 1
)

REM Run the setup script
python setup_fresh_repo.py

echo.
echo Setup completed. Press any key to exit...
pause >nul
