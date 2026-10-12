@echo off
:: Foreclosure Agent — Daily launcher for Windows Task Scheduler
:: Logs stdout+stderr to logs\YYYY-MM-DD.log

setlocal

:: Project root = this script's folder (survives moving the folder)
set PROJECT_DIR=%~dp0
set PROJECT_DIR=%PROJECT_DIR:~0,-1%

:: Optional: activate virtual environment (uncomment if using venv)
:: call "%PROJECT_DIR%\.venv\Scripts\activate.bat"

:: Date stamp for log file
for /f "tokens=1-3 delims=/" %%a in ("%date%") do (
    set LOGDATE=%%c-%%a-%%b
)

set LOGFILE=%PROJECT_DIR%\logs\%LOGDATE%.log

cd /d "%PROJECT_DIR%"
python main.py >> "%LOGFILE%" 2>&1

endlocal
