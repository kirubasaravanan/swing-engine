@echo off
chcp 65001
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo Starting Swing Decision Bot (Automated Mode)...
echo Logs will be written to swing_bot.log

"C:\Users\user\AppData\Local\Programs\Python\Python312\python.exe" -X utf8 swing_bot.py
pause
pause
