@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ===== GAN STOP-LOSS CHO VI THE MEXC (ban tu xac nhan) =====
python mexc_sl.py %*
echo.
pause
