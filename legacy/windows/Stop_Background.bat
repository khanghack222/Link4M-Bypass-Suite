@echo off
title DUNG TIEN TRINH CHAY NGAM AUTO BYPASS
echo ===================================================
echo     DANG DUNG CAC TIEN TRINH BYPASS CHAY NGAM...
echo ===================================================
taskkill /F /IM python.exe /FI "WINDOWTITLE eq Auto_Bypass*" 2>nul
taskkill /F /IM wscript.exe 2>nul
echo.
echo [OK] Da dung tat ca tien trinh Auto Bypass chay ngam!
timeout /t 3 >nul
