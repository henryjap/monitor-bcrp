@echo off
setlocal
title MAXIMIXE DataBank INEI
cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"
set "PORT=8502"
set "URL=http://localhost:%PORT%"

if not exist "%PYTHON_EXE%" (
    echo No se encontro el entorno local .venv.
    echo Ejecute primero reinstalar_dependencias.bat o prepare el entorno Python.
    pause
    exit /b 1
)

for /f %%P in ('powershell -NoProfile -Command "$p=%PORT%; while(Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue){ $p++ }; $p"') do set "PORT=%%P"
set "URL=http://localhost:%PORT%"

echo.
echo Iniciando MAXIMIXE DataBank INEI...
echo Se abrira el navegador en %URL%
echo Cierra esta ventana para apagar la app INEI.
echo.

powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process '%URL%'" >nul 2>nul
"%PYTHON_EXE%" -m streamlit run app_inei.py --server.port %PORT% --server.headless true --browser.gatherUsageStats false

endlocal
