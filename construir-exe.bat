@echo off
chcp 65001 > nul
setlocal
title Construir ejecutable

cd /d "%~dp0"

set "VENV=.venv"
set "PY_EXE=%VENV%\Scripts\python.exe"
set "SALIDA=dist\NotaVideo.exe"

echo.
echo  ═══════════════════════════════════════════════
echo    Construir el ejecutable (.exe)
echo  ═══════════════════════════════════════════════
echo.
echo  Genera UN SOLO archivo que funciona en cualquier PC
echo  con Windows, sin instalar Python ni nada mas.
echo.
echo  Tarda 2-4 minutos. Vuelve a ejecutarlo cada vez que
echo  cambies el codigo.
echo.

rem ffmpeg viaja dentro del .exe: sin el, la descarga de videos queda
rem limitada a la calidad que YouTube entregue ya combinada (unos 360p).
if exist "ffmpeg.exe" goto :hay_ffmpeg
where ffmpeg >nul 2>&1
if not errorlevel 1 goto :hay_ffmpeg

echo  [!] No se encontro ffmpeg en el sistema.
echo      El .exe se construira igual, pero solo podra descargar
echo      videos en la calidad baja que YouTube entrega ya combinada.
echo.
echo      Para incluirlo: winget install yt-dlp.FFmpeg
echo      o deja ffmpeg.exe y ffprobe.exe junto a este archivo.
echo.
choice /c SN /n /m "  ¿Construir de todos modos? (S/N): "
if errorlevel 2 exit /b 1
echo.

:hay_ffmpeg

if not exist "%PY_EXE%" (
    echo  [X] No existe el entorno virtual.
    echo      Ejecuta primero iniciar.bat.
    echo.
    pause
    exit /b 1
)

rem PyInstaller solo hace falta para construir, no para usar la app
"%PY_EXE%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo  Instalando PyInstaller...
    "%PY_EXE%" -m pip install pyinstaller --quiet --disable-pip-version-check
    if errorlevel 1 goto :error
    echo.
)

echo  Construyendo...
echo.

rem La receta esta en NotaVideo.spec: ahi se define el .exe unico y se
rem recogen los extractores de yt-dlp, que se cargan de forma dinamica
"%PY_EXE%" -m PyInstaller --noconfirm NotaVideo.spec
if errorlevel 1 goto :error
if not exist "%SALIDA%" goto :error

echo.
echo  ═══════════════════════════════════════════════
echo    Listo
echo  ═══════════════════════════════════════════════
echo.
for %%F in ("%SALIDA%") do echo    %%~fF  (%%~zF bytes)
echo.
echo  Es un archivo unico y autonomo: se puede subir, enviar
echo  o copiar tal cual. No necesita carpetas al lado.
echo.
echo  Lleva ffmpeg incorporado, por eso pesa mas de 100 MB.
echo.

choice /c SN /n /m "  ¿Abrir la carpeta ahora? (S/N): "
if not errorlevel 2 start "" "dist"

echo.
exit /b 0

:error
echo.
echo  [X] Fallo la construccion.
echo      El detalle del error esta mas arriba.
echo.
pause
exit /b 1
