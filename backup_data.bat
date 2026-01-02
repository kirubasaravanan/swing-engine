@echo off
echo ==============================================
echo      SWING ENGINE DATA BACKUP UTILITY
echo ==============================================
echo.
echo [1/3] Adding ALL data to Git...
git add .

echo.
echo [2/3] Committing Snapshot...
git commit -m "Data Backup: %date% %time%"

echo.
echo [3/3] Pushing to Cloud...
git push

echo.
echo ==============================================
echo        BACKUP COMPLETE! ☁️
echo ==============================================
echo You can now safely close this window.
pause
