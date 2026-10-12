@echo off
:: Bolt Deals PPC Sheet -- sync launcher for Windows Task Scheduler
::
:: Runs every 15 minutes. Claude desktop drops the three REsimpli exports
:: (Active / Warm / Dead, filtered to Bolt PPC) into Downloads on its own
:: schedule; this picks them up shortly after they land, whenever that is.
::
:: Safe to run constantly: processed files are archived, so there is nothing
:: left to re-sync, and any CSV that is not a lead export is refused.
::
:: Logging is handled inside daily_sync.py (logs\YYYY-MM-DD.log) and is written
:: ONLY when a run actually did something -- 96 idle ticks a day would
:: otherwise bury the runs that mattered. Batch does not build the log name
:: because %date% here is "Tue 08/18/2026" and splitting it on "/" produced
:: a log called "2026-Tue 08-18.log".
::
:: Exit codes: 0 ok (or idle) | 2 python missing | 3 uncaught error

setlocal

set PROJECT_DIR=%~dp0
set PROJECT_DIR=%PROJECT_DIR:~0,-1%

:: Absolute path -- Task Scheduler does not inherit an interactive PATH.
set PYTHON=C:\Users\jsive\AppData\Local\Programs\Python\Python313\python.exe

:: REsimpli statuses contain non-ANSI characters (the star in "* Albert
:: Bucket"). Without this, printing them raises UnicodeEncodeError.
set PYTHONIOENCODING=utf-8

set DOWNLOADS=%USERPROFILE%\Downloads

:: Safety guard. Keeps only rows whose Lead Source or Campaign contains this.
:: All 159 Bolt leads carry Campaign Name "Bolt PPC", so "bolt" keeps every one
:: of them while rejecting Direct Mail / Cold Calling / Website leads.
::
:: This is not belt-and-braces paranoia: a stray mixed export already in
:: Downloads (Exported_Leads_123051, 223 rows) would have put 210 non-PPC leads
:: into the vendor's sheet with this empty. Verified 2026-08-18.
::
:: Failure mode if REsimpli renames the campaign: zero rows match, daily_sync
:: refuses to archive and exits non-zero. Loud, not silent. That is the point.
set SOURCE_MATCH=bolt

:: Ignore exports older than this, so a silently failed export is NOT papered
:: over by re-syncing yesterday's file.
set MAX_AGE=26

cd /d "%PROJECT_DIR%"

if not exist "%PYTHON%" (
    echo FATAL: python not found at %PYTHON%
    endlocal
    exit /b 2
)

"%PYTHON%" daily_sync.py --downloads-dir "%DOWNLOADS%" --source-match "%SOURCE_MATCH%" --max-age-hours %MAX_AGE% --apply
set RC=%errorlevel%

:: rc 1 = nothing valid to sync. Normal for most ticks; report success so the
:: Task Scheduler history does not fill with false failures.
if "%RC%"=="1" set RC=0

endlocal & exit /b %RC%
