@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== DAT LENH MEXC (ban tu xac nhan tung lenh) =====
python mexc_entry.py %*
echo.
pause
