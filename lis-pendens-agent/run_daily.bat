@echo off
cd /d "%~dp0"
python enhanced_master_script.py >> lis_pendens_automation.log 2>&1
echo Ran at %date% %time% >> heartbeat.log
