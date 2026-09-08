# -*- mode: python ; coding: utf-8 -*-
"""Receta de empaquetado de NotaVideo.

Genera un unico .exe autonomo. Se usa desde construir-exe.bat.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

BASE = Path(SPECPATH)

datas, binaries, hiddenimports = [], [], []

# yt-dlp trae cientos de extractores que se cargan de forma dinamica:
# sin collect_all, PyInstaller no los detecta y el .exe no descarga nada.
for paquete in ("yt_dlp", "anthropic"):
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
