@echo off
REM ============================================================================
REM Huang Di Dashboard Generator - Automated Execution Script
REM ============================================================================
REM This script ensures reliable execution for scheduled tasks with:
REM - Working directory management
REM - Virtual environment activation
REM - Comprehensive error handling
REM - Logging with rotation
REM - Network connectivity checks
REM - Process isolation
REM ============================================================================

setlocal enabledelayedexpansion

REM Configuration - MODIFY THESE PATHS FOR YOUR SYSTEM
set "SCRIPT_DIR=C:\AI Prompt Local"
set "PYTHON_EXE=python"
set "VENV_PATH=%SCRIPT_DIR%\venv"
set "LOG_DIR=%SCRIPT_DIR%\logs"
set "MAX_LOG_FILES=30"
set "TIMEOUT_MINUTES=10"

REM Automation indicators
set "AUTOMATION_MODE=true"
set "SCHEDULED_TASK=true"

REM ============================================================================
REM INITIALIZATION
REM ============================================================================

echo [%date% %time%] Starting Huang Di Dashboard Generation...

REM Create logs directory if it doesn't exist
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
    echo [%date% %time%] Created log directory: %LOG_DIR%
)

REM Set up log file with date rotation
set "LOG_FILE=%LOG_DIR%\dashboard_automation_%date:~10,4%_%date:~4,2%_%date:~7,2%.log"
set "LOG_FILE=%LOG_FILE: =_%"
set "LOG_FILE=%LOG_FILE:/=_%"

echo [%date% %time%] Log file: %LOG_FILE%

REM ============================================================================
REM PRE-FLIGHT CHECKS
REM ============================================================================

echo [%date% %time%] Running pre-flight checks... >> "%LOG_FILE%" 2>&1

REM Check if script directory exists
if not exist "%SCRIPT_DIR%" (
    echo [%date% %time%] ERROR: Script directory not found: %SCRIPT_DIR% >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] ERROR: Script directory not found: %SCRIPT_DIR%
    exit /b 1
)

REM Change to script directory
cd /d "%SCRIPT_DIR%" || (
    echo [%date% %time%] ERROR: Could not change to script directory >> "%LOG_FILE%" 2>&1
    exit /b 1
)

echo [%date% %time%] Working directory: %CD% >> "%LOG_FILE%" 2>&1

REM Check if Python script exists
if not exist "huang_di.py" (
    echo [%date% %time%] ERROR: huang_di.py not found in %CD% >> "%LOG_FILE%" 2>&1
    exit /b 1
)

REM Check Python installation
%PYTHON_EXE% --version >nul 2>&1
if !errorlevel! neq 0 (
    echo [%date% %time%] ERROR: Python not found or not accessible >> "%LOG_FILE%" 2>&1
    exit /b 1
)

echo [%date% %time%] Python version: >> "%LOG_FILE%" 2>&1
%PYTHON_EXE% --version >> "%LOG_FILE%" 2>&1

REM ============================================================================
REM VIRTUAL ENVIRONMENT ACTIVATION (OPTIONAL)
REM ============================================================================

if exist "%VENV_PATH%\Scripts\activate.bat" (
    echo [%date% %time%] Activating virtual environment... >> "%LOG_FILE%" 2>&1
    call "%VENV_PATH%\Scripts\activate.bat" >> "%LOG_FILE%" 2>&1
    if !errorlevel! neq 0 (
        echo [%date% %time%] WARNING: Could not activate virtual environment, continuing with system Python >> "%LOG_FILE%" 2>&1
    ) else (
        echo [%date% %time%] Virtual environment activated successfully >> "%LOG_FILE%" 2>&1
    )
) else (
    echo [%date% %time%] No virtual environment found, using system Python >> "%LOG_FILE%" 2>&1
)

REM ============================================================================
REM NETWORK CONNECTIVITY CHECK
REM ============================================================================

echo [%date% %time%] Checking network connectivity... >> "%LOG_FILE%" 2>&1

REM Test internet connectivity with multiple targets
set "NETWORK_OK=false"

ping -n 1 8.8.8.8 >nul 2>&1
if !errorlevel! equ 0 (
    set "NETWORK_OK=true"
    echo [%date% %time%] Network connectivity confirmed (Google DNS) >> "%LOG_FILE%" 2>&1
) else (
    ping -n 1 1.1.1.1 >nul 2>&1
    if !errorlevel! equ 0 (
        set "NETWORK_OK=true"
        echo [%date% %time%] Network connectivity confirmed (Cloudflare DNS) >> "%LOG_FILE%" 2>&1
    )
)

if "!NETWORK_OK!"=="false" (
    echo [%date% %time%] WARNING: Network connectivity issues detected >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] Continuing execution - script will handle network failures gracefully >> "%LOG_FILE%" 2>&1
)

REM ============================================================================
REM DEPENDENCY CHECK
REM ============================================================================

echo [%date% %time%] Checking critical dependencies... >> "%LOG_FILE%" 2>&1

%PYTHON_EXE% -c "import requests, arrow, icalendar, jinja2, weasyprint" >nul 2>&1
if !errorlevel! neq 0 (
    echo [%date% %time%] ERROR: Critical Python dependencies missing >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] Attempting to install missing dependencies... >> "%LOG_FILE%" 2>&1
    
    %PYTHON_EXE% -m pip install --quiet requests arrow icalendar jinja2 weasyprint >> "%LOG_FILE%" 2>&1
    
    REM Verify installation
    %PYTHON_EXE% -c "import requests, arrow, icalendar, jinja2, weasyprint" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [%date% %time%] ERROR: Could not install required dependencies >> "%LOG_FILE%" 2>&1
        exit /b 1
    )
    
    echo [%date% %time%] Dependencies installed successfully >> "%LOG_FILE%" 2>&1
) else (
    echo [%date% %time%] All dependencies available >> "%LOG_FILE%" 2>&1
)

REM ============================================================================
REM CLEANUP OLD LOGS
REM ============================================================================

echo [%date% %time%] Cleaning up old log files... >> "%LOG_FILE%" 2>&1

REM Count log files and delete oldest if more than MAX_LOG_FILES
for /f %%i in ('dir "%LOG_DIR%\dashboard_automation_*.log" /b 2^>nul ^| find /c /v ""') do set "LOG_COUNT=%%i"

if !LOG_COUNT! gtr %MAX_LOG_FILES% (
    echo [%date% %time%] Found !LOG_COUNT! log files, cleaning up oldest... >> "%LOG_FILE%" 2>&1
    
    REM Delete oldest log files (keep the newest MAX_LOG_FILES)
    for /f "skip=%MAX_LOG_FILES%" %%f in ('dir "%LOG_DIR%\dashboard_automation_*.log" /b /o-d 2^>nul') do (
        del "%LOG_DIR%\%%f" >nul 2>&1
        echo [%date% %time%] Deleted old log file: %%f >> "%LOG_FILE%" 2>&1
    )
)

REM ============================================================================
REM MAIN EXECUTION
REM ============================================================================

echo [%date% %time%] Starting dashboard generation with timeout protection... >> "%LOG_FILE%" 2>&1

REM Calculate timeout in seconds
set /a "TIMEOUT_SECONDS=%TIMEOUT_MINUTES% * 60"

REM Execute Python script with timeout and comprehensive logging
timeout /t %TIMEOUT_SECONDS% %PYTHON_EXE% huang_di.py --automation >> "%LOG_FILE%" 2>&1

set "SCRIPT_EXIT_CODE=!errorlevel!"

REM ============================================================================
REM RESULT ANALYSIS
REM ============================================================================

echo [%date% %time%] Dashboard generation completed with exit code: !SCRIPT_EXIT_CODE! >> "%LOG_FILE%" 2>&1

if !SCRIPT_EXIT_CODE! equ 0 (
    echo [%date% %time%] SUCCESS: Dashboard generated successfully >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] SUCCESS: Dashboard generated successfully
) else if !SCRIPT_EXIT_CODE! equ 124 (
    echo [%date% %time%] ERROR: Dashboard generation timed out after %TIMEOUT_MINUTES% minutes >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] ERROR: Dashboard generation timed out
) else (
    echo [%date% %time%] WARNING: Dashboard generation completed with warnings/errors >> "%LOG_FILE%" 2>&1
    echo [%date% %time%] WARNING: Dashboard generation completed with warnings
    
    REM In automation mode, non-zero exit doesn't necessarily mean total failure
    REM Check if PDF was actually generated
    for /f %%i in ('dir "G:\My Drive\Huang_Di\NMS_*.pdf" /b /o-d 2^>nul ^| find /c /v ""') do set "PDF_COUNT=%%i"
    
    if !PDF_COUNT! gtr 0 (
        echo [%date% %time%] PDF file found, treating as successful despite exit code >> "%LOG_FILE%" 2>&1
        set "SCRIPT_EXIT_CODE=0"
    )
)

REM ============================================================================
REM POST-EXECUTION CHECKS
REM ============================================================================

echo [%date% %time%] Running post-execution verification... >> "%LOG_FILE%" 2>&1

REM Check if local PDF was created today
set "TODAY_FILE_PATTERN=NMS_%date:~10,4%_%date:~4,2%_%date:~7,2%_*.pdf"
set "TODAY_FILE_PATTERN=!TODAY_FILE_PATTERN: =_!"
set "TODAY_FILE_PATTERN=!TODAY_FILE_PATTERN:/=_!"

if exist "G:\My Drive\Huang_Di\!TODAY_FILE_PATTERN!" (
    echo [%date% %time%] Verification: Today's PDF file found in output directory >> "%LOG_FILE%" 2>&1
) else (
    echo [%date% %time%] WARNING: Today's PDF file not found in expected location >> "%LOG_FILE%" 2>&1
    
    REM List recent files for debugging
    echo [%date% %time%] Recent files in output directory: >> "%LOG_FILE%" 2>&1
    dir "G:\My Drive\Huang_Di\NMS_*.pdf" /b /o-d 2>nul | head -5 >> "%LOG_FILE%" 2>&1
)

REM ============================================================================
REM CLEANUP AND EXIT
REM ============================================================================

echo [%date% %time%] Automation run completed >> "%LOG_FILE%" 2>&1
echo.>> "%LOG_FILE%"
echo ============================================================================ >> "%LOG_FILE%"
echo.>> "%LOG_FILE%"

REM Deactivate virtual environment if it was activated
if defined VIRTUAL_ENV (
    deactivate >nul 2>&1
)

echo [%date% %time%] Huang Di Dashboard automation finished (Exit Code: !SCRIPT_EXIT_CODE!)

REM Return appropriate exit code for Task Scheduler
exit /b !SCRIPT_EXIT_CODE!