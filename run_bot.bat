@echo off
echo Starting Swing Decision Bot...
echo Logs will be written to swing_bot.log
cd /d "%~dp0"
call .venv\Scripts\activate
python swing_bot.py
pause
