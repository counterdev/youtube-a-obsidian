@echo off
chcp 65001 > nul
setlocal
title NotaVideo

cd /d "%~dp0"

set "VENV=.venv"
set "PY_EXE=%VENV%\Scripts\python.exe"

echo.
echo  ═══════════════════════════════════════════════
echo    NotaVideo — de YouTube a Obsidian
echo  ═══════════════════════════════════════════════
echo.

if not exist "%PY_EXE%" (
    echo  Primera vez: preparando el entorno...
    echo.

    python --version >nul 2>&1
    if errorlevel 1 (
        echo  [X] No se encontro Python.
        echo      Instalalo desde python.org y marca la casilla
        echo      "Add Python to PATH" durante la instalacion.
        echo.
        pause
        exit /b 1
    )

    python -m venv "%VENV%"
    if errorlevel 1 goto :error

    "%PY_EXE%" -m pip install --upgrade pip --quiet --disable-pip-version-check
    echo  Instalando dependencias...
    "%PY_EXE%" -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 goto :error

    echo  Listo.
    echo.
)

rem Completa las dependencias si el entorno viene de una version anterior.
"%PY_EXE%" -c "import yt_dlp, anthropic, openai" >nul 2>&1
if errorlevel 1 (
    echo  Completando dependencias...
    "%PY_EXE%" -m pip install -r requirements.txt --quiet --disable-pip-version-check
    if errorlevel 1 goto :error
)

"%PY_EXE%" notavideo_app.py
if errorlevel 1 goto :error

exit /b 0

:error
echo.
echo  [X] Algo fallo. El detalle esta mas arriba.
echo.
pause
exit /b 1
