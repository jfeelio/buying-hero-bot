@echo off
set LOG_DIR=%~dp0logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set LOG_FILE=%LOG_DIR%\tax_deed_%date:~10,4%-%date:~4,2%-%date:~7,2%.log

echo [%date% %time%] Starting Tax Deed Agent >> "%LOG_FILE%"
cd /d "%~dp0"

python main_tax_deed.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Done >> "%LOG_FILE%"
