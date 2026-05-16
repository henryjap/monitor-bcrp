@echo off
setlocal
title Reinstalar dependencias Monitor MAXIMIXE Data
cd /d "%~dp0"

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
    %PY_BOOTSTRAP% -m venv .venv
)

.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
    echo.
    echo No se pudieron reinstalar las dependencias.
    pause
    exit /b 1
)

echo ok > ".venv\.deps_installed"
echo.
echo Dependencias actualizadas.
pause
endlocal
