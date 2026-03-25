@echo off
cd /d "%~dp0"
python main_probate.py >> "logs\probate_%DATE:~-4,4%-%DATE:~-10,2%-%DATE:~-7,2%.log" 2>&1
