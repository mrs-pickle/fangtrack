@echo off
title FangTrack Pro
cd /d "%~dp0"
echo.
echo  ==========================================
echo    FANGTRACK PRO — Market Intelligence
echo    Opening at http://localhost:5000
echo    Press Ctrl+C to stop
echo  ==========================================
echo.
python app.py
pause
