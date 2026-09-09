# -*- mode: python ; coding: utf-8 -*-
"""Receta de empaquetado de NotaVideo.

Genera un unico .exe autonomo. Se usa desde construir-exe.bat.
"""
import shutil
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

BASE = Path(SPECPATH)

datas, binaries, hiddenimports = [], [], []


def buscar_ffmpeg(programa):
    """Ubica un binario de ffmpeg: primero el del repo, luego el del sistema."""
    local = BASE / f"{programa}.exe"
    if local.is_file():
        return str(local)
    return shutil.which(programa)


# ffmpeg viaja dentro del .exe porque sin el no se pueden unir las pistas de
# video y audio, que YouTube sirve separadas por encima de 360p. ffprobe lo
# acompana: yt-dlp lo usa para inspeccionar los formatos antes de unirlos.
for programa in ("ffmpeg", "ffprobe"):
    ruta = buscar_ffmpeg(programa)
    if ruta:
        binaries += [(ruta, ".")]
    else:
        print(f"AVISO: no se encontro {programa}. El .exe solo podra descargar "
              f"videos en la calidad que YouTube entregue ya combinada.")

# yt-dlp trae cientos de extractores que se cargan de forma dinamica:
# sin collect_all, PyInstaller no los detecta y el .exe no descarga nada.
for paquete in ("yt_dlp", "anthropic", "openai"):
    d, b, h = collect_all(paquete)
    datas += d
    binaries += b
    hiddenimports += h

# Los prompts viajan dentro del .exe como respaldo. Si el usuario copia las
# plantillas a su boveda, la app prefiere esas.
datas += [(str(BASE / "prompts"), "prompts")]

if (BASE / "icono.ico").is_file():
    datas += [(str(BASE / "icono.ico"), ".")]

a = Analysis(
    [str(BASE / "notavideo_app.py")],
    pathex=[str(BASE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Nada de esto se usa y sumaria cientos de MB al ejecutable.
    excludes=["PyInstaller", "numpy", "pandas", "matplotlib", "PIL",
              "pytest", "setuptools", "test"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="NotaVideo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(BASE / "icono.ico") if (BASE / "icono.ico").is_file() else None,
)
