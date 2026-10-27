# -*- mode: python ; coding: utf-8 -*-
"""Bundle the standalone player, frame data, configuration, audio, and icons into an EXE."""

import os
from PyInstaller.utils.hooks import collect_all

datas_pg, binaries_pg, hiddenimports_pg = collect_all('pygame')

# Resolve all asset paths dynamically relative to this spec file directory
def spec_asset(filename):
    return os.path.join(SPECPATH, filename)

datas = []
for asset in ['config.json', 'ascii_data.npz', 'audio.wav', 'README.txt', 'eye_icon.png', 'eye_icon.ico']:
    asset_path = spec_asset(asset)
    if os.path.exists(asset_path):
        datas.append((asset_path, '.'))

datas += datas_pg

icon_path = spec_asset('eye_icon.ico')
exe_icon = icon_path if os.path.exists(icon_path) else None

a = Analysis(
    [spec_asset('run.py')],
    pathex=[SPECPATH],
    binaries=binaries_pg,
    datas=datas,
    hiddenimports=hiddenimports_pg + ['numpy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'cv2', 'av', 'PIL'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ASCII_Player',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=exe_icon,
    disable_windowed_traceback=False,
)
