# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

import os
# window/taskbar + EXE icon: drop assets/icon.ico in and rebuild; without it Windows shows the default icon
HAS_ICON = os.path.exists('assets/icon.ico')
datas = [('assets/icon.ico', 'assets')] if HAS_ICON else []
datas.append(('v2/dist', 'v2/dist'))
binaries = []
hiddenimports = []
# pywebview / pythonnet (WebView2 via WinForms) are handled by pyinstaller-hooks-contrib;
# pynput picks its backend at runtime, so collect it fully.
tmp_ret = collect_all('pynput')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'shiboken6', 'PyQt5', 'PyQt6', 'qtpy', 'tkinter',  # app is Qt-free
              'numpy', 'PIL', 'cryptography'],  # optional extras pulled in by hooks (cryptography = pywebview ssl only)
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NotAFK',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.ico'] if HAS_ICON else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NotAFK',
)
