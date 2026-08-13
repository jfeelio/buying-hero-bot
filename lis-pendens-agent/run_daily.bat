@echo off
cd /d "D:\Dropbox\J Feels\Dev\lis-pendens-agent"
python enhanced_master_script.py >> lis_pendens_automation.log 2>&1
echo Ran at %date% %time% >> heartbeat.log
