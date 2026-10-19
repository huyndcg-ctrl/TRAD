@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== HUY LENH CHO MEXC (ban tu xac nhan) =====
python mexc_cancel.py %*
echo.
pause
