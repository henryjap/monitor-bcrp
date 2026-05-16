@echo off
setlocal
title MAXIMIXE DataBank
cd /d "%~dp0"

set "PYTHON_EXE=.venv\Scripts\python.exe"
set "PIP_EXE=.venv\Scripts\python.exe -m pip"
set "PORT="
set "URL=http://localhost:%PORT%"

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo.
        echo No se encontro Python en esta PC.
        echo Instale Python 3.10 o superior desde https://www.python.org/downloads/
        echo IMPORTANTE: durante la instalacion marque "Add python.exe to PATH".
        echo.
        pause
        exit /b 1
    ) else (
        set "PY_BOOTSTRAP=py -3"
    )
) else (
    set "PY_BOOTSTRAP=python"
)

if not exist ".venv" (
    echo Preparando entorno Python local...
    %PY_BOOTSTRAP% -m venv .venv
    if errorlevel 1 (
        echo.
        echo No se pudo crear el entorno local .venv.
        pause
        exit /b 1
    )
)

if not exist ".venv\.deps_installed" (
    echo Instalando dependencias por unica vez...
    %PIP_EXE% install --upgrade pip
    %PIP_EXE% install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo No se pudieron instalar las dependencias.
        pause
        exit /b 1
    )
    echo ok > ".venv\.deps_installed"
)

for /f %%P in ('powershell -NoProfile -Command "$p=8501; while(Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue){ $p++ }; $p"') do set "PORT=%%P"
set "URL=http://localhost:%PORT%"

echo.
echo Iniciando MAXIMIXE DataBank...
echo Se abrira el navegador en %URL%
echo Cierra esta ventana para apagar la app.
echo.

powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process '%URL%'" >nul 2>nul
%PYTHON_EXE% -m streamlit run app.py --server.port %PORT% --server.headless true --browser.gatherUsageStats false

endlocal
