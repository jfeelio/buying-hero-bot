@echo off
:: Foreclosure Agent — Daily launcher for Windows Task Scheduler
:: Logs stdout+stderr to logs\YYYY-MM-DD.log

setlocal

:: Project root (update if you move the folder)
set PROJECT_DIR=D:\Dropbox\J Feels\Dev\foreclosure-agent

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
