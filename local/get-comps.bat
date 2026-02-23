@echo off
REM Kiavi ARV comp puller for Windows
REM Usage: get-comps.bat "123 Main St, Miami, FL 33101" 200000 45000

set ADDRESS=%~1
set PURCHASE=%~2
set REHAB=%~3

if "%ADDRESS%"=="" (
    echo ERROR: No address provided
    exit /b 1
)

node "%~dp0..\kiavi-arv.js" "%ADDRESS%" "%PURCHASE%" "%REHAB%"
