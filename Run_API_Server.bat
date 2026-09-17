@echo off
chcp 65001 >nul
title LINK4M BYPASS SUITE - MICROSERVICE API SERVER (FASTAPI)
echo =====================================================================
echo  ⚡ LINK4M / BYPASS SUITE - MICROSERVICE API SERVER ⚡
echo  Port: 8000 (OpenAPI Docs: http://127.0.0.1:8000/docs)
echo =====================================================================

set "PY311=C:\Users\XUAN\AppData\Local\Programs\Python\Python311\python.exe"

if exist "%PY311%" (
    echo [*] Sử dụng Python 3.11: %PY311%
    "%PY311%" -m uvicorn api_server:app --host 0.0.0.0 --port 8000
) else (
    echo [*] Sử dụng Python hệ thống...
    python -m uvicorn api_server:app --host 0.0.0.0 --port 8000
)

pause
